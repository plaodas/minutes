import logging
import os

from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import update_task_success


def reconcile_once(outputs_dir: str | None = None) -> None:
    """Scan DB tasks and outputs folder, and map an unreferenced output to a single pending task.

    This function is best-effort: DB errors are logged and result in an empty tasks map.
    """
    logger = logging.getLogger("minutes.reconcile")
    outputs_dir = outputs_dir or os.environ.get("OUTPUTS_DIR", "outputs")

    # Load tasks from the DB only. Do not fall back to a file-based store.
    tasks: dict[str, dict] = {}
    try:
        from minutes.db import session_scope
        from minutes.models import Task

        with session_scope() as session:
            for t in session.query(Task).all():
                tasks[str(t.id)] = {
                    "status": t.status,
                    "result": t.result or {},
                    "fail_count": int(t.fail_count or 0),
                    "last_failure_ts": (
                        t.last_failure_ts.isoformat() + "Z"
                        if t.last_failure_ts
                        else None
                    ),
                    "last_success_ts": (
                        t.last_success_ts.isoformat() + "Z"
                        if t.last_success_ts
                        else None
                    ),
                }
    except SQLAlchemyError:
        logger.exception("failed to load tasks for reconciliation")
        tasks = {}

    pending = [tid for tid, v in tasks.items() if v.get("status") == "pending"]

    # gather referenced outputs
    referenced: set[str] = set()
    for v in tasks.values():
        r = v.get("result") or {}
        of = r.get("output_file")
        if of:
            referenced.add(os.path.basename(of))

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


if __name__ == "__main__":
    reconcile_once()
