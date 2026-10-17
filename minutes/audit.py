"""Persist a single audit row for an action that changes access or data."""

import logging
import os
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from minutes.auth import (
    decode_access_token,
    get_current_user_from_cookie,
    get_user_by_id,
    resolve_service_token,
)
from minutes.db import session_scope
from minutes.models import AuditEvent

logger = logging.getLogger("minutes.audit")


@dataclass(frozen=True)
class Actor:
    kind: str
    user_id: uuid.UUID | None = None
    token_id: uuid.UUID | None = None


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _bearer_value(header: str | None) -> str | None:
    if not header:
        return None
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1]
    return header


def _admin_override(request: Request | None) -> bool:
    force_admin = os.environ.get("FORCE_ADMIN", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    legacy_admin = request.headers.get("X-Admin") if request else None
    return bool(
        force_admin
        or legacy_admin == "1"
        or (isinstance(legacy_admin, str) and legacy_admin.lower() == "true")
    )


def actor_from_admin_request(request: Request | None) -> Actor:
    """Resolve the actor in the same order as ``require_admin``."""
    if _admin_override(request):
        return Actor("admin_override")

    presented = None
    if request:
        presented = _bearer_value(
            request.headers.get("X-Admin-Token") or request.headers.get("Authorization")
        )
    configured_token = os.environ.get("ADMIN_API_TOKEN")
    if configured_token and presented == configured_token:
        return Actor("admin_token")

    if request:
        cookie = request.cookies.get("minutes_session")
        if cookie:
            try:
                user = get_current_user_from_cookie(cookie)
            except HTTPException:
                user = None
            if user and user.is_admin:
                return Actor("session", user.id)

        authorization = _bearer_value(request.headers.get("Authorization"))
        if authorization:
            try:
                payload = decode_access_token(authorization)
                user_id = payload.get("sub")
                user = get_user_by_id(str(user_id)) if user_id else None
                if user and user.is_admin:
                    return Actor("session", user.id)
            except (HTTPException, ValueError, TypeError):
                logger.debug("JWT decode/lookup failed while recording audit")

            resolved = resolve_service_token(authorization)
            if resolved:
                token_id, owner_id = resolved
                user = get_user_by_id(str(owner_id)) if owner_id else None
                if user and user.is_admin:
                    return Actor("service_token", owner_id, token_id)

    return Actor("admin_override")


def actor_from_user_request(request: Request | None, user) -> Actor:
    """Resolve the actor in the same order as ``require_current_user``.

    A cookie that identifies the already loaded user is a session. An invalid
    cookie falls through to the bearer service token.
    """
    if request is not None:
        cookie = request.cookies.get("minutes_session")
        if cookie:
            try:
                payload = decode_access_token(cookie)
            except HTTPException:
                payload = None
            subject = payload.get("sub") if payload else None
            if subject and user is not None and str(user.id) == str(subject):
                return Actor("session", user.id)

        authorization = _bearer_value(request.headers.get("Authorization"))
        if authorization:
            resolved = resolve_service_token(authorization)
            if resolved:
                token_id, owner_id = resolved
                return Actor(
                    "service_token",
                    owner_id or getattr(user, "id", None),
                    token_id,
                )

    if user is not None and getattr(user, "id", None) is not None:
        return Actor("session", user.id)
    return Actor("session")


def record_audit(
    *,
    action: str,
    actor: Actor,
    target_type: str,
    target_id: str,
    detail: dict | None = None,
    session=None,
) -> None:
    """Insert one audit row.

    Pass ``session`` to join the caller's transaction. Otherwise this opens its
    own. A failure of that separate write is logged and does not propagate.
    """
    event = AuditEvent(
        action=action,
        actor_kind=actor.kind,
        actor_user_id=_as_uuid(actor.user_id),
        actor_token_id=_as_uuid(actor.token_id),
        target_type=target_type,
        target_id=str(target_id),
        detail=dict(detail) if detail is not None else None,
    )
    if session is not None:
        session.add(event)
        return
    try:
        with session_scope() as db:
            db.add(event)
    except SQLAlchemyError:
        logger.exception("audit write failed action=%s target=%s", action, target_id)
