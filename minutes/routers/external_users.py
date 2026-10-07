import logging

from fastapi import APIRouter, Header
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from minutes.auth import match_provision_secret, provision_external_user
from minutes.http_errors import error_json
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    ExternalUserProvisionRequest,
    ExternalUserProvisionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/external", tags=["external"])


def _valid_external_id(value: str) -> bool:
    return bool(value.strip()) and len(value) <= 255


@router.post(
    "/users",
    response_model=ExternalUserProvisionResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        401: JSON_ERROR_RESPONSES[401],
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def create_external_user(
    payload: ExternalUserProvisionRequest,
    authorization: str | None = Header(None),
):
    matched = match_provision_secret(authorization)
    if matched is None:
        return error_json("not found", 404)
    if not matched:
        return error_json("invalid credentials", 401)
    if not _valid_external_id(payload.external_id):
        return error_json("invalid external_id", 400)
    try:
        user_id, token, token_id = provision_external_user(payload.external_id)
    except (IntegrityError, SQLAlchemyError):
        logger.exception("Failed to provision external user")
        return error_json("request failed", 500)
    return {"user_id": user_id, "token": token, "token_id": token_id}
