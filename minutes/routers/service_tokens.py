import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

from minutes.audit import actor_from_admin_request, record_audit
from minutes.auth import create_service_token
from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import ServiceToken, User
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    RevokedResponse,
    ServiceTokenCreatedResponse,
    ServiceTokenListResponse,
)

router = APIRouter(prefix="/api/service-tokens", tags=["service-tokens"])


class CreateServiceTokenRequest(BaseModel):
    name: str | None = None
    user_id: str | None = None


def token_rows(session, user_id=None):
    query = session.query(ServiceToken, User.username).outerjoin(
        User, ServiceToken.user_id == User.id
    )
    if user_id is not None:
        query = query.filter(ServiceToken.user_id == user_id)
    return query.all()


def present_token(token: ServiceToken, username: str | None) -> dict:
    return {
        "id": str(token.id),
        "name": token.name,
        "user_id": str(token.user_id) if token.user_id else None,
        "username": username,
        "revoked": bool(token.revoked),
        "created_at": token.created_at.isoformat() if token.created_at else None,
    }


@router.post(
    "",
    response_model=ServiceTokenCreatedResponse,
    responses={400: JSON_ERROR_RESPONSES[400]},
)
def create_token(payload: CreateServiceTokenRequest, request: Request = None):
    try:
        token, token_id = create_service_token(
            name=payload.name,
            user_id=payload.user_id,
        )
    except ValueError as exc:
        return error_json(str(exc), 400)
    record_audit(
        action="service_token.create",
        actor=actor_from_admin_request(request),
        target_type="service_token",
        target_id=token_id,
        detail={"name": payload.name, "user_id": payload.user_id},
    )
    return {"token": token, "id": token_id}


@router.get("", response_model=ServiceTokenListResponse)
def list_tokens():
    with session_scope() as session:
        return {
            "tokens": [
                present_token(token, username)
                for token, username in token_rows(session)
            ]
        }


@router.delete(
    "/{token_id}",
    response_model=RevokedResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        404: JSON_ERROR_RESPONSES[404],
    },
)
def revoke_token(token_id: str, request: Request = None):
    try:
        key = uuid.UUID(token_id)
    except (ValueError, TypeError):
        return error_json("invalid token id", 400)

    actor = actor_from_admin_request(request)
    with session_scope() as session:
        token = session.get(ServiceToken, key)
        if not token:
            return error_json("not found", 404)
        token.revoked = True
        record_audit(
            action="service_token.revoke",
            actor=actor,
            target_type="service_token",
            target_id=str(token.id),
            detail={
                "name": token.name,
                "user_id": str(token.user_id) if token.user_id else None,
            },
            session=session,
        )
        return {"revoked": True}
