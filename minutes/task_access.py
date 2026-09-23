import uuid

from minutes.db import session_scope
from minutes.models import Task, User
from minutes.task_state import parse_task_key


def user_owns_task(task_id: str, user_id: uuid.UUID) -> bool:
    """Return whether the task exists and belongs to the user."""
    key = parse_task_key(task_id)
    if not isinstance(key, uuid.UUID):
        return False
    with session_scope() as session:
        task = session.get(Task, key)
        return bool(task and task.user_id == user_id)


def owned_task_ids(task_ids: list[uuid.UUID], user_id: uuid.UUID) -> set[uuid.UUID]:
    if not task_ids:
        return set()
    with session_scope() as session:
        rows = (
            session.query(Task.id)
            .filter(Task.id.in_(task_ids), Task.user_id == user_id)
            .all()
        )
    return {row[0] for row in rows}


def snapshot_owned_by(task: object, user: User) -> bool:
    if not isinstance(task, dict):
        return False
    return str(task.get("user_id") or "") == str(user.id)


def event_visible_to(
    event: object,
    user_id: uuid.UUID,
    cache: dict[str, bool],
) -> bool:
    """Keep events whose task belongs to the connected user."""
    task_id = event.get("task_id") if isinstance(event, dict) else None
    if not task_id:
        return False
    key = str(task_id)
    if key not in cache:
        cache[key] = user_owns_task(key, user_id)
    return cache[key]
