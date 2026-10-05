import logging
import os
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import update_task_success
from minutes.task_result import result_output_file

logger = logging.getLogger("minutes.reconcile")


def reconcile_once(outputs_dir: str | None = None) -> None:
    """Scan DB tasks and outputs folder, and map an unreferenced output to a single pending task.

    This function is best-effort: DB errors are logged and result in an empty tasks map.
    """
    outputs_dir = outputs_dir or os.environ.get("OUTPUTS_DIR", "outputs")

    # Load tasks from the DB only. Do not fall back to a file-based store.
    tasks = _load_tasks()
    if tasks is None:
        tasks = {}

    pending = [tid for tid, v in tasks.items() if v.get("status") == "pending"]
    referenced = _referenced_output_names(tasks)

    # list outputs
    if not os.path.isdir(outputs_dir):
        logger.error("outputs dir not found: %s", outputs_dir)
        return
    files = [f for f in os.listdir(outputs_dir) if f.lower().startswith("minutes_")]
    unreferenced = [f for f in files if f not in referenced]

    logger.info("pending tasks: %s", pending)
    logger.info("referenced outputs: %s", referenced)
    logger.info("outputs in dir: %s", files)
    logger.info("unreferenced outputs: %s", unreferenced)

    # if exactly one pending and one unreferenced, assign it
    if len(pending) == 1 and len(unreferenced) == 1:
        tid = pending[0]
        out = os.path.join(outputs_dir, unreferenced[0])
        logger.info("Mapping output %s -> task %s", out, tid)
        update_task_success(tid, {"output_file": out})
        logger.info("Updated task to success")
        return

    logger.info("No unambiguous mapping found; no changes made.")


def quarantine_unreferenced_outputs(
    outputs_dir: str | None = None,
    now: datetime | None = None,
) -> None:
    """Move old unreferenced minutes files aside, then delete expired quarantined files.

    A failed task read leaves every file in place.
    """
    outputs_dir = outputs_dir or os.environ.get("OUTPUTS_DIR", "outputs")
    moment = now or datetime.now(tz=timezone.utc)
    tasks = _load_tasks()
    if tasks is None:
        logger.error("skipping output quarantine; tasks were not loaded")
        return
    if not os.path.isdir(outputs_dir):
        logger.error("outputs dir not found: %s", outputs_dir)
        return

    referenced = _referenced_output_names(tasks)
    quarantine_seconds = int(os.environ.get("OUTPUT_QUARANTINE_SECONDS", "21600"))
    retention_seconds = int(os.environ.get("OUTPUT_DELETED_RETENTION_SECONDS", "86400"))
    quarantine_cutoff = moment.timestamp() - quarantine_seconds
    deleted_dir = os.path.join(outputs_dir, "deleted")
    moved: set[str] = set()

    for name in os.listdir(outputs_dir):
        if not name.lower().startswith("minutes_"):
            continue
        source = os.path.join(outputs_dir, name)
        if not os.path.isfile(source) or name in referenced:
            continue
        try:
            if os.path.getmtime(source) > quarantine_cutoff:
                continue
            os.makedirs(deleted_dir, exist_ok=True)
            destination = os.path.join(deleted_dir, name)
            if os.path.exists(destination):
                logger.error("quarantine destination already exists: %s", destination)
                continue
            os.rename(source, destination)
            os.utime(destination, (moment.timestamp(), moment.timestamp()))
            moved.add(name)
            logger.info("Quarantined unreferenced output %s", destination)
        except OSError:
            logger.exception("failed to quarantine output %s", source)

    if not os.path.isdir(deleted_dir):
        return
    retention_cutoff = moment.timestamp() - retention_seconds
    for name in os.listdir(deleted_dir):
        if name in moved:
            continue
        path = os.path.join(deleted_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) <= retention_cutoff:
                os.remove(path)
                logger.info("Removed expired quarantined output %s", path)
        except OSError:
            logger.exception("failed to remove quarantined output %s", path)


def _load_tasks() -> dict[str, dict] | None:
    try:
        from minutes.db import session_scope
        from minutes.models import Task

        tasks: dict[str, dict] = {}
        with session_scope() as session:
            for task in session.query(Task).all():
                tasks[str(task.id)] = {
                    "status": task.status,
                    "result": task.result or {},
                    "fail_count": int(task.fail_count or 0),
                    "last_failure_ts": (
                        task.last_failure_ts.isoformat() + "Z"
                        if task.last_failure_ts
                        else None
                    ),
                    "last_success_ts": (
                        task.last_success_ts.isoformat() + "Z"
                        if task.last_success_ts
                        else None
                    ),
                }
        return tasks
    except SQLAlchemyError:
        logger.exception("failed to load tasks for reconciliation")
        return None


def _referenced_output_names(tasks: dict[str, dict]) -> set[str]:
    referenced: set[str] = set()
    for task in tasks.values():
        output_file = result_output_file(task.get("result"))
        if output_file:
            referenced.add(os.path.basename(output_file))
    return referenced


if __name__ == "__main__":
    reconcile_once()
