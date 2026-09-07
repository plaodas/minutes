import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, status
from passlib.hash import pbkdf2_sha256
from fastapi import Depends

from minutes.db import SessionLocal
from minutes.models import User


# Configuration
SECRET_KEY = os.environ.get("JWT_SECRET") or os.environ.get("ADMIN_API_TOKEN") or "dev-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "8"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pbkdf2_sha256.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def create_access_token(sub: str, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = {"sub": str(sub)}
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")


def get_user_by_id(user_id: str) -> Optional[User]:
    try:
        db = SessionLocal()
        try:
            uid = uuid.UUID(user_id)
        except Exception:
            return None
        return db.get(User, uid)
    finally:
        try:
            db.close()
        except Exception:
            pass


def get_current_user_from_cookie(token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        return None
    return get_user_by_id(sub)


def require_current_user(minutes_session: Optional[str] = Cookie(None)) -> User:
    """FastAPI dependency to require a logged-in user via the `minutes_session` cookie.

    Raises HTTP 401 if not authenticated.
    """
    user = get_current_user_from_cookie(minutes_session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
