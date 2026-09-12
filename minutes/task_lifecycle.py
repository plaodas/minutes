from datetime import datetime, timezone

from minutes.models import Task
from minutes.task_event_service import TaskEventService
from minutes.task_events import emit_task_event


class _TaskNotFoundError(Exception):
    pass


def mark_task_deleted(task_id: str) -> bool:
    def delete_task(session, key):
        task = session.get(Task, key)
        if not task:
            raise _TaskNotFoundError

        previous_status = task.status
        task.status = "deleted"
        task.deleted = True
        task.deleted_at = datetime.now(tz=timezone.utc)
        session.add(task)
        return previous_status

    try:
        TaskEventService(emit_task_event).record_and_publish(
            task_id,
            "deleted",
            lambda previous: {"previous": previous},
            mutate=delete_task,
        )
    except _TaskNotFoundError:
        return False
    return True


def restore_task(task_id: str) -> bool:
    def undelete_task(session, key):
        task = session.get(Task, key)
        if not task:
            raise _TaskNotFoundError

        restored_status = "success" if task.result else "pending"
        previous_status = task.status
        task.status = restored_status
        task.deleted = False
        task.deleted_at = None
        session.add(task)
        return previous_status, restored_status

    try:
        TaskEventService(emit_task_event).record_and_publish(
            task_id,
            "undeleted",
            lambda statuses: {
                "previous": statuses[0],
                "status": statuses[1],
            },
            mutate=undelete_task,
        )
    except _TaskNotFoundError:
        return False
    return True
