import logging
import os

from fastapi import APIRouter, Cookie, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from minutes.auth import (
    create_access_token,
    get_current_user_from_cookie,
    verify_password,
)
from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import User
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    AuthFeaturesResponse,
    AuthLoginRequest,
    AuthLoginResponse,
    AuthLogoutResponse,
)

logger = logging.getLogger("minutes.routers.authentication")
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/features", response_model=AuthFeaturesResponse)
def auth_features(
    x_admin: str | None = Header(None),
    minutes_session: str | None = Cookie(None),
):
    try:
        force_admin = os.environ.get("FORCE_ADMIN", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        header_admin = x_admin == "1" or (
            isinstance(x_admin, str) and x_admin.lower() == "true"
        )
        try:
            user = get_current_user_from_cookie(minutes_session)
        except (HTTPException, ValueError, TypeError):
            user = None

        admin = bool(force_admin or header_admin or (user and user.is_admin))
        return {"is_admin": admin, "authenticated": user is not None}
    except (ValueError, AttributeError, TypeError):
        return {"is_admin": False, "authenticated": False}


@router.post(
    "/login",
    response_model=AuthLoginResponse,
    responses={401: JSON_ERROR_RESPONSES[401]},
)
def login(payload: AuthLoginRequest, response: Response):
    logger.debug("Login attempt for username=%s", payload.username)
    with session_scope() as session:
        try:
            user = (
                session.query(User)
                .filter(User.username == payload.username)
                .one_or_none()
            )
        except SQLAlchemyError:
            user = None

        if not user:
            logger.warning("Failed login: unknown user %s", payload.username)
            return error_json("invalid credentials", 401)

        try:
            if not user.password_hash or not verify_password(
                payload.password,
                user.password_hash,
            ):
                logger.warning(
                    "Failed login: bad password for user %s", payload.username
                )
                return error_json("invalid credentials", 401)
        except (ValueError, TypeError):
            logger.exception("Failed login verification for %s", payload.username)
            return error_json("invalid credentials", 401)

        token = create_access_token(str(user.id))
        secure = os.environ.get("ENV", "").lower() == "production" or os.environ.get(
            "FORCE_HTTPS",
            "false",
        ).lower() in {"1", "true"}
        result = JSONResponse(
            AuthLoginResponse(
                id=str(user.id),
                is_admin=bool(user.is_admin),
            ).model_dump()
        )
        result.set_cookie(
            "minutes_session",
            token,
            httponly=True,
            samesite="lax",
            secure=secure,
            max_age=int(os.environ.get("JWT_EXPIRE_HOURS", "8")) * 3600,
        )
        logger.info("User logged in: username=%s id=%s", payload.username, user.id)
        return result


@router.post("/logout", response_model=AuthLogoutResponse)
def logout(response: Response):
    logger.info("Logout requested")
    result = JSONResponse(AuthLogoutResponse(logged_out=True).model_dump())
    result.delete_cookie("minutes_session")
    return result
