import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, HTTPException, status
from passlib.hash import pbkdf2_sha256

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


def require_current_user(minutes_session: str | None = Cookie(None)) -> User:
    """FastAPI dependency to require a logged-in user via the `minutes_session` cookie.

    Raises HTTP 401 if not authenticated.
    """
    user = get_current_user_from_cookie(minutes_session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_service_token(name: str | None = None, user_id: str | None = None):
    """Create a new service token, store its hash in DB, return plaintext token and model id."""
    token = uuid.uuid4().hex + uuid.uuid4().hex
    token_hash = _hash_token(token)
    with session_scope() as db:
        st = ServiceToken(name=name, token_hash=token_hash)
        if user_id:
            try:
                st.user_id = uuid.UUID(user_id)
            except (ValueError, TypeError):
                pass
        db.add(st)
        db.flush()
        return token, str(st.id)


def verify_service_token(token: str):
    """Verify provided token string; return associated user_id UUID or None."""
    if not token:
        return None
    # accept Bearer tokens
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
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
            return None
        return st.user_id
