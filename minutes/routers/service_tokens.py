import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from minutes.auth import create_service_token
from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import ServiceToken
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


@router.post("", response_model=ServiceTokenCreatedResponse)
def create_token(payload: CreateServiceTokenRequest):
    token, token_id = create_service_token(
        name=payload.name,
        user_id=payload.user_id,
    )
    return {"token": token, "id": token_id}


@router.get("", response_model=ServiceTokenListResponse)
def list_tokens():
    with session_scope() as session:
        tokens = session.query(ServiceToken).all()
        return {
            "tokens": [
                {
                    "id": str(token.id),
                    "name": token.name,
                    "user_id": str(token.user_id) if token.user_id else None,
                    "revoked": bool(token.revoked),
                    "created_at": (
                        token.created_at.isoformat() if token.created_at else None
                    ),
                }
                for token in tokens
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
def revoke_token(token_id: str):
    try:
        key = uuid.UUID(token_id)
    except (ValueError, TypeError):
        return error_json("invalid token id", 400)

    with session_scope() as session:
        token = session.get(ServiceToken, key)
        if not token:
            return error_json("not found", 404)
        token.revoked = True
        return {"revoked": True}
