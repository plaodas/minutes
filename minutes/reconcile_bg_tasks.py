import os
import json
from minutes.bg_store import DB_PATH, get_task, update_task_success, update_task_failure


def reconcile_once(outputs_dir="data/outputs"):
    # Load tasks from the DB only. Do not fall back to a file-based store.
    tasks = {}
    try:
        from minutes.db import SessionLocal
        from minutes.models import Task
        session = SessionLocal()
        try:
            for t in session.query(Task).all():
                tasks[str(t.id)] = {
                    "status": t.status,
                    "result": t.result or {},
                    "fail_count": int(t.fail_count or 0),
                    "last_failure_ts": t.last_failure_ts.isoformat() + "Z" if t.last_failure_ts else None,
                    "last_success_ts": t.last_success_ts.isoformat() + "Z" if t.last_success_ts else None,
                }
        finally:
            try:
                session.close()
            except Exception:
                pass
    except Exception:
        tasks = {}

    pending = [tid for tid, v in tasks.items() if v.get("status") == "pending"]
    # gather referenced outputs
    referenced = set()
    for v in tasks.values():
        r = v.get("result") or {}
        of = r.get("output_file")
        if of:
            referenced.add(os.path.basename(of))

    # list outputs
    if not os.path.isdir(outputs_dir):
        print("outputs dir not found:", outputs_dir)
        return
    files = [f for f in os.listdir(outputs_dir) if f.lower().startswith("minutes_")]
    unreferenced = [f for f in files if f not in referenced]

    print("pending tasks:", pending)
    print("referenced outputs:", referenced)
    print("outputs in dir:", files)
    print("unreferenced outputs:", unreferenced)

    # if exactly one pending and one unreferenced, assign it
    if len(pending) == 1 and len(unreferenced) == 1:
        tid = pending[0]
        out = os.path.join(outputs_dir, unreferenced[0])
        print(f"Mapping output {out} -> task {tid}")
        update_task_success(tid, {"output_file": out})
        print("Updated task to success")
        return

    print("No unambiguous mapping found; no changes made.")


if __name__ == "__main__":
    reconcile_once()
