from fastapi import APIRouter

from minutes.db import session_scope
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


@router.get("", response_model=AuditEventListResponse)
def list_audit_events(
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
):
    query_action = _present(action)
    query_target_type = _present(target_type)
    query_target_id = _present(target_id)
    bounded = _bounded_limit(limit)
    with session_scope() as session:
        query = session.query(AuditEvent)
        if query_action:
            query = query.filter(AuditEvent.action == query_action)
        if query_target_type:
            query = query.filter(AuditEvent.target_type == query_target_type)
        if query_target_id:
            query = query.filter(AuditEvent.target_id == query_target_id)
        rows = (
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(bounded)
            .all()
        )
        return {
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
            ]
        }
