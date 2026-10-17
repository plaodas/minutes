from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import and_, or_

from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import AuditEvent
from minutes.schemas import AuditEventListResponse

router = APIRouter(prefix="/api/audit-events", tags=["audit-events"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 200


def _present(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _bounded_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > MAX_LIMIT:
        return MAX_LIMIT
    return limit


def _cursor(
    before_created_at: str | None, before_id: int | None
) -> tuple[datetime, int] | None:
    created_at = _present(before_created_at)
    if created_at is None and before_id is None:
        return None
    if created_at is None or before_id is None:
        raise ValueError("invalid audit cursor")
    try:
        moment = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise ValueError("invalid audit cursor") from exc
    return moment, before_id


@router.get("", response_model=AuditEventListResponse)
def list_audit_events(
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    before_created_at: str | None = None,
    before_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
):
    query_action = _present(action)
    query_target_type = _present(target_type)
    query_target_id = _present(target_id)
    try:
        cursor = _cursor(before_created_at, before_id)
    except ValueError:
        return error_json("invalid audit cursor", 400)
    bounded = _bounded_limit(limit)
    with session_scope() as session:
        query = session.query(AuditEvent)
        if query_action:
            query = query.filter(AuditEvent.action == query_action)
        if query_target_type:
            query = query.filter(AuditEvent.target_type == query_target_type)
        if query_target_id:
            query = query.filter(AuditEvent.target_id == query_target_id)
        if cursor is not None:
            moment, event_id = cursor
            query = query.filter(
                or_(
                    AuditEvent.created_at < moment,
                    and_(
                        AuditEvent.created_at == moment,
                        AuditEvent.id < event_id,
                    ),
                )
            )
        rows = (
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(bounded + 1)
            .all()
        )
        has_more = len(rows) > bounded
        rows = rows[:bounded]
        return {
            "has_more": has_more,
            "events": [
                {
                    "id": str(row.id),
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                    "action": row.action,
                    "actor_kind": row.actor_kind,
                    "actor_user_id": (
                        str(row.actor_user_id) if row.actor_user_id else None
                    ),
                    "actor_token_id": (
                        str(row.actor_token_id) if row.actor_token_id else None
                    ),
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "detail": row.detail,
                }
                for row in rows
            ],
        }
