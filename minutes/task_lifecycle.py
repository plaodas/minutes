from datetime import datetime, timezone

from minutes.db import session_scope
from minutes.models import Task, TaskHistory
from minutes.task_events import emit_task_event
from minutes.task_state import parse_task_key


def mark_task_deleted(task_id: str) -> bool:
    with session_scope() as db:
        key = parse_task_key(task_id)
        task = db.get(Task, key)
        if not task:
            return False

        payload = {"previous": task.status}
        task.status = "deleted"
        task.deleted = True
        task.deleted_at = datetime.now(tz=timezone.utc)
        db.add(TaskHistory(task_id=key, event_type="deleted", payload=payload))

    emit_task_event(task_id, "deleted", payload)
    return True


def restore_task(task_id: str) -> bool:
    with session_scope() as db:
        key = parse_task_key(task_id)
        task = db.get(Task, key)
        if not task:
            return False

        restored_status = "success" if task.result else "pending"
        payload = {"previous": task.status, "status": restored_status}
        task.status = restored_status
        task.deleted = False
        task.deleted_at = None
        db.add(TaskHistory(task_id=key, event_type="undeleted", payload=payload))

    emit_task_event(task_id, "undeleted", payload)
    return True
