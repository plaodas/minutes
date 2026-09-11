#!/usr/bin/env python3
"""Poll `minutes.bg_store.get_task` for a given task id until completion.

Usage: python scripts/poll_task_status.py <task_id>
"""

import json
import sys
import time
from datetime import datetime, timezone

try:
    from minutes.bg_store import get_task
except (ImportError, ModuleNotFoundError) as e:
    print("Failed to import minutes.bg_store.get_task:", e)
    sys.exit(2)

try:
    from sqlalchemy.exc import SQLAlchemyError
except (ImportError, ModuleNotFoundError):
    SQLAlchemyError = Exception


def now_iso():
    # return an ISO timestamp with UTC tzinfo
    return datetime.now(tz=timezone.utc).isoformat()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/poll_task_status.py <task_id>")
        return 2
    task_id = sys.argv[1]
    max_iters = 600  # ~20 minutes at 2s sleep
    for i in range(max_iters):
        try:
            t = get_task(task_id)
        except (SQLAlchemyError, OSError, ValueError) as e:
            # DB or I/O related error while reading task; log and continue
            print(f"{now_iso()} ERROR reading task: {e}")
            t = None
        if t is None:
            print(f"{now_iso()} {i}: task not found")
        else:
            status = t.get("status")
            progress = t.get("progress")
            print(f"{now_iso()} {i}: status={status} progress={progress}")
        sys.stdout.flush()
        if t and status in ("success", "failed"):
            break
        time.sleep(2)

    print("FINAL:")
    try:
        print(json.dumps(get_task(task_id), indent=2, ensure_ascii=False))
    except (SQLAlchemyError, OSError, ValueError) as e:
        print("FINAL read error:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
