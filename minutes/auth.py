import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Header, HTTPException, status
from passlib.hash import pbkdf2_sha256
from sqlalchemy.exc import IntegrityError

from minutes.db import session_scope
from minutes.models import ServiceToken, User

# Configuration
SECRET_KEY = (
    os.environ.get("JWT_SECRET") or os.environ.get("ADMIN_API_TOKEN") or "dev-secret"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "8"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pbkdf2_sha256.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def create_access_token(sub: str, expires_delta: timedelta | None = None) -> str:
    to_encode = {"sub": str(sub)}
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


def get_user_by_id(user_id: str) -> User | None:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        return None
    with session_scope() as db:
        return db.get(User, uid)


def get_current_user_from_cookie(token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        return None
    return get_user_by_id(sub)


def require_current_user(
    minutes_session: str | None = Cookie(None),
    authorization: str | None = Header(None),
) -> User:
    """Require the session cookie or a service token bound to a user.

    Client-supplied user ids are ignored. Raises HTTP 401 if neither
    credential identifies a user.
    """
    user = None
    try:
        user = get_current_user_from_cookie(minutes_session)
    except HTTPException:
        user = None
    if user:
        return user

    token = authorization
    if token and token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    if token:
        try:
            owner_id = verify_service_token(token)
        except (ValueError, TypeError):
            owner_id = None
        if owner_id:
            user = get_user_by_id(str(owner_id))
            if user:
                return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_service_token(name: str | None = None, user_id: str | None = None, db=None):
    """Create a new service token, store its hash in DB, return plaintext token and model id.

    Pass ``db`` to insert inside the caller's transaction. Otherwise this opens its own.
    """
    token = uuid.uuid4().hex + uuid.uuid4().hex
    token_hash = _hash_token(token)

    def insert(session):
        service_token = ServiceToken(name=name, token_hash=token_hash, revoked=False)
        if user_id:
            try:
                service_token.user_id = uuid.UUID(user_id)
            except (ValueError, TypeError):
                pass
        session.add(service_token)
        session.flush()
        return token, str(service_token.id)

    if db is not None:
        return insert(db)
    with session_scope() as session:
        return insert(session)


def match_provision_secret(authorization: str | None) -> bool | None:
    """Return None when provisioning is disabled, otherwise whether the secret matches.

    The comparison hashes both values so the secret itself is not logged or branched on length.
    """
    expected = os.environ.get("PROVISION_SECRET") or ""
    if not expected.strip():
        return None
    presented = authorization or ""
    if presented.lower().startswith("bearer "):
        presented = presented.split(" ", 1)[1]
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    presented_digest = hashlib.sha256(presented.encode("utf-8")).digest()
    return hmac.compare_digest(expected_digest, presented_digest)


def provision_external_user(external_id: str) -> tuple[str, str, str]:
    """Find or create the external user, revoke active tokens, and issue one new token."""
    last_error: IntegrityError | None = None
    for _attempt in range(2):
        try:
            with session_scope() as db:
                user = (
                    db.query(User)
                    .filter(User.external_subject == external_id)
                    .one_or_none()
                )
                if user is None:
                    user = User(
                        username=f"ext-{uuid.uuid4().hex}",
                        password_hash=get_password_hash(secrets.token_urlsafe(32)),
                        is_admin=False,
                        external_subject=external_id,
                    )
                    db.add(user)
                    db.flush()
                (
                    db.query(ServiceToken)
                    .filter(
                        ServiceToken.user_id == user.id,
                        ServiceToken.revoked.is_(False),
                    )
                    .update({ServiceToken.revoked: True}, synchronize_session=False)
                )
                token, token_id = create_service_token(
                    name="external",
                    user_id=str(user.id),
                    db=db,
                )
                return str(user.id), token, token_id
        except IntegrityError as exc:
            last_error = exc
    if last_error is None:
        raise RuntimeError("external user provision failed")
    raise last_error


def verify_service_token(token: str):
    """Verify provided token string; return associated user_id UUID or None."""
    logger = logging.getLogger("minutes.auth")
    if not token:
        return None
    # accept Bearer tokens
    if isinstance(token, str) and token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    try:
        fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    except (AttributeError, TypeError, UnicodeEncodeError):
        fp = "<hash-error>"
    logger.info("verify_service_token: attempt fingerprint=%s", fp)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.info("verify_service_token: attempt fingerprint=%s", fp)
    token_hash = _hash_token(token)
    with session_scope() as db:
        st = (
            db.query(ServiceToken)
            .filter(
                ServiceToken.token_hash == token_hash, ServiceToken.revoked == False
            )
            .one_or_none()
        )
        if not st:
            logger.debug("verify_service_token: not found fingerprint=%s", fp)
            uvicorn_logger = logging.getLogger("uvicorn.error")
            uvicorn_logger.debug("verify_service_token: not found fingerprint=%s", fp)
            return None
        logger.info(
            "verify_service_token: matched token_id=%s user_id=%s fingerprint=%s",
            str(st.id),
            str(st.user_id),
            fp,
        )
        uvicorn_logger = logging.getLogger("uvicorn.error")
        uvicorn_logger.info(
            "verify_service_token: matched token_id=%s user_id=%s fingerprint=%s",
            str(st.id),
            str(st.user_id),
            fp,
        )
        return st.user_id
