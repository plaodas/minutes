import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from minutes.audit import actor_from_user_request, record_audit
from minutes.auth import create_service_token, require_current_user
from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import ServiceToken, User
from minutes.routers.service_tokens import present_token, token_rows
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    RevokedResponse,
    ServiceTokenCreatedResponse,
    ServiceTokenListResponse,
)

router = APIRouter(prefix="/api/my/service-tokens", tags=["my-service-tokens"])


class CreateMyServiceTokenRequest(BaseModel):
    name: str | None = None
    user_id: str | None = None


@router.get("", response_model=ServiceTokenListResponse)
def list_my_tokens(user: User = Depends(require_current_user)):  # noqa: B008
    with session_scope() as session:
        return {
            "tokens": [
                present_token(token, username)
                for token, username in token_rows(session, user.id)
            ]
        }


@router.post(
    "",
    response_model=ServiceTokenCreatedResponse,
    responses={400: JSON_ERROR_RESPONSES[400]},
)
def create_my_token(
    payload: CreateMyServiceTokenRequest,
    request: Request = None,
    user: User = Depends(require_current_user),  # noqa: B008
):
    actor = actor_from_user_request(request, user)
    owner_id = str(user.id)
    try:
        with session_scope() as session:
            token, token_id = create_service_token(
                name=payload.name,
                user_id=owner_id,
                db=session,
            )
            record_audit(
                action="service_token.create",
                actor=actor,
                target_type="service_token",
                target_id=token_id,
                detail={"name": payload.name, "user_id": owner_id},
                session=session,
            )
            return {"token": token, "id": token_id}
    except ValueError as exc:
        return error_json(str(exc), 400)


@router.delete(
    "/{token_id}",
    response_model=RevokedResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        404: JSON_ERROR_RESPONSES[404],
    },
)
def revoke_my_token(
    token_id: str,
    request: Request = None,
    user: User = Depends(require_current_user),  # noqa: B008
):
    try:
        key = uuid.UUID(token_id)
    except (ValueError, TypeError):
        return error_json("invalid token id", 400)

    actor = actor_from_user_request(request, user)
    with session_scope() as session:
        token = session.get(ServiceToken, key)
        if not token or token.user_id != user.id:
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
