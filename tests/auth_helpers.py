import uuid

from fastapi.testclient import TestClient

from minutes.auth import create_access_token, get_password_hash
from minutes.db import session_scope
from minutes.models import Task, User


def create_user(username: str | None = None) -> uuid.UUID:
    user_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            User(
                id=user_id,
                username=username or f"user-{user_id.hex[:12]}",
                password_hash=get_password_hash("secret"),
                is_admin=False,
            )
        )
    return user_id


def login(client: TestClient, user_id: uuid.UUID) -> TestClient:
    client.cookies.set("minutes_session", create_access_token(str(user_id)))
    return client


def logged_in_client(app, username: str | None = None) -> tuple[TestClient, uuid.UUID]:
    user_id = create_user(username)
    return login(TestClient(app), user_id), user_id


def assign_task_owner(task_id: uuid.UUID | str, user_id: uuid.UUID) -> None:
    key = task_id if isinstance(task_id, uuid.UUID) else uuid.UUID(str(task_id))
    with session_scope() as session:
        task = session.get(Task, key)
        if task is None:
            raise AssertionError(f"missing task {key}")
        task.user_id = user_id
