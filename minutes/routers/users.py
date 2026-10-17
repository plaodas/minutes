from fastapi import APIRouter

from minutes.db import session_scope
from minutes.models import User
from minutes.schemas import UserListResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users():
    with session_scope() as session:
        users = session.query(User).order_by(User.username).all()
        return {
            "users": [{"id": str(user.id), "username": user.username} for user in users]
        }
