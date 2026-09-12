import hashlib
import logging
import os
import uuid

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from .auth import (
    decode_access_token,
    get_current_user_from_cookie,
    get_user_by_id,
    verify_service_token,
)
from .task_state import parse_task_key

logger = logging.getLogger("minutes.request_auth")


def parse_header_user_id(
    x_user_id: str | None,
    authorization: str | None = None,
) -> uuid.UUID | None:
    if x_user_id:
        parsed = parse_task_key(x_user_id)
        return parsed if isinstance(parsed, uuid.UUID) else None

    if not authorization:
        return None
    token = authorization
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    try:
        user_id = verify_service_token(token)
    except (SQLAlchemyError, TypeError, ValueError):
        logger.exception(
            "Error resolving service token fingerprint=%s",
            fingerprint,
        )
        return None
    if not user_id:
        logger.debug("Service token not recognized fingerprint=%s", fingerprint)
        return None
    logger.info(
        "Service token resolved to user=%s fingerprint=%s",
        user_id,
        fingerprint,
    )
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None


def is_request_admin(
    x_admin: str | None,
    authorization: str | None = None,
) -> bool:
    try:
        force_admin = os.environ.get("FORCE_ADMIN", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        header_admin = x_admin == "1" or (
            isinstance(x_admin, str) and x_admin.lower() == "true"
        )
        if force_admin or header_admin:
            return True
        if not authorization:
            return False

        token = authorization
        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            user = get_user_by_id(str(user_id)) if user_id else None
            if user and user.is_admin:
                return True
        except (HTTPException, ValueError, TypeError):
            logger.debug("JWT decode/lookup failed")

        try:
            user_id = verify_service_token(token)
            user = get_user_by_id(str(user_id)) if user_id else None
            return bool(user and user.is_admin)
        except (SQLAlchemyError, TypeError, ValueError):
            return False
    except (ValueError, AttributeError, TypeError):
        return False


def require_admin(request: Request = None) -> bool:
    force_admin = os.environ.get("FORCE_ADMIN", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    legacy_admin = request.headers.get("X-Admin") if request else None
    if (
        force_admin
        or legacy_admin == "1"
        or (isinstance(legacy_admin, str) and legacy_admin.lower() == "true")
    ):
        return True

    token = None
    if request:
        token = request.headers.get("X-Admin-Token") or request.headers.get(
            "Authorization"
        )
    if token and token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    configured_token = os.environ.get("ADMIN_API_TOKEN")
    if configured_token and token == configured_token:
        return True

    if request:
        cookie = request.cookies.get("minutes_session")
        if cookie:
            try:
                user = get_current_user_from_cookie(cookie)
                if user and user.is_admin:
                    return True
            except (HTTPException, ValueError, TypeError):
                logger.debug("Cookie authentication failed")

        authorization = request.headers.get("Authorization")
        if authorization and is_request_admin(None, authorization):
            return True

    raise HTTPException(status_code=403, detail="forbidden")
