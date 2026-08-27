import json
import threading
import os
from typing import Optional, Dict, Any

_lock = threading.Lock()
DB_PATH = os.environ.get("BG_TASK_DB", "data/bg_tasks.json")


def _read_db() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}


def _write_db(data: Dict[str, Any]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_task(task_id: str):
    with _lock:
        db = _read_db()
        db[task_id] = {"status": "pending", "result": None, "error": None, "progress": None,
                       "fail_count": 0, "last_failure_ts": None, "last_failure_error": None, "last_success_ts": None}
        _write_db(db)


def update_task_success(task_id: str, result: Any):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "success"
        db[task_id]["result"] = result
        db[task_id]["error"] = None
        db[task_id]["progress"] = 100.0
        db[task_id]["fail_count"] = 0
        from datetime import datetime
        db[task_id]["last_success_ts"] = datetime.utcnow().isoformat() + "Z"
        _write_db(db)


def update_task_failure(task_id: str, error_msg: str):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "failed"
        db[task_id]["result"] = None
        db[task_id]["error"] = error_msg
        db[task_id]["progress"] = None
        # update failure metrics
        cnt = db[task_id].get("fail_count") or 0
        try:
            db[task_id]["fail_count"] = int(cnt) + 1
        except Exception:
            db[task_id]["fail_count"] = 1
        from datetime import datetime
        db[task_id]["last_failure_ts"] = datetime.utcnow().isoformat() + "Z"
        db[task_id]["last_failure_error"] = error_msg
        _write_db(db)


def update_task_cancelled(task_id: str):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "cancelled"
        db[task_id]["result"] = None
        db[task_id]["error"] = "cancelled by user"
        db[task_id]["progress"] = None
        # do not count as failure, but note timestamp
        from datetime import datetime
        db[task_id]["last_failure_ts"] = None
        db[task_id]["last_failure_error"] = "cancelled by user"
        _write_db(db)


def update_task_status(task_id: str, status: str):
    """Set an arbitrary status string for the task (e.g. 'preprocess', 'transcribing').

    This is intentionally simple: callers should use a small controlled set
    of status strings to indicate progress stages. Existing helpers
    `update_task_success`/`update_task_failure` still set final states.
    """
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = status
        # when updating status, optionally clear or set progress separately
        _write_db(db)


def update_task_progress(task_id: str, progress: float):
    """Set progress as a percentage (0.0-100.0)."""
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["progress"] = float(progress)
        _write_db(db)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        db = _read_db()
        return db.get(task_id)
