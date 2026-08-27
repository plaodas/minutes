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
        db[task_id] = {"status": "pending", "result": None, "error": None}
        _write_db(db)


def update_task_success(task_id: str, result: Any):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "success"
        db[task_id]["result"] = result
        db[task_id]["error"] = None
        _write_db(db)


def update_task_failure(task_id: str, error_msg: str):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "failed"
        db[task_id]["result"] = None
        db[task_id]["error"] = error_msg
        _write_db(db)


def update_task_cancelled(task_id: str):
    with _lock:
        db = _read_db()
        db.setdefault(task_id, {})
        db[task_id]["status"] = "cancelled"
        db[task_id]["result"] = None
        db[task_id]["error"] = "cancelled by user"
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
        _write_db(db)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        db = _read_db()
        return db.get(task_id)
