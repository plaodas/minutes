import os
import threading
from typing import Optional, Dict, Any

_lock = threading.Lock()
DB_PATH = os.environ.get("BG_TASK_DB", "data/bg_tasks.json")

# If a DATABASE_URL is present, prefer DB-backed store
USE_DB = bool(os.environ.get("DATABASE_URL"))

if USE_DB:
    from .db import SessionLocal
    from .models import Task, TaskHistory
    from sqlalchemy.exc import NoResultFound
    from datetime import datetime

    def get_session():
        """Return a new DB session (caller should close it)."""
        return SessionLocal()

    def create_task(task_id: str, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = Task(id=task_id, status="pending", progress=None, result=None, fail_count=0)
                db.add(t)
                db.commit()
            finally:
                if close:
                    db.close()


    def update_task_success(task_id: str, result: Any, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = db.query(Task).get(task_id)
                if not t:
                    t = Task(id=task_id)
                    db.add(t)
                t.status = "success"
                t.result = result
                t.progress = 100.0
                t.fail_count = 0
                t.last_success_ts = datetime.utcnow()
                db.commit()
            finally:
                if close:
                    db.close()


    def update_task_failure(task_id: str, error_msg: str, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = db.query(Task).get(task_id)
                if not t:
                    t = Task(id=task_id)
                    db.add(t)
                t.status = "failed"
                t.result = None
                t.fail_count = (t.fail_count or 0) + 1
                t.last_failure_ts = datetime.utcnow()
                db.commit()
            finally:
                if close:
                    db.close()


    def update_task_cancelled(task_id: str, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = db.query(Task).get(task_id)
                if not t:
                    t = Task(id=task_id)
                    db.add(t)
                t.status = "cancelled"
                t.result = None
                db.commit()
            finally:
                if close:
                    db.close()


    def update_task_status(task_id: str, status: str, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = db.query(Task).get(task_id)
                if not t:
                    t = Task(id=task_id)
                    db.add(t)
                t.status = status
                db.commit()
            finally:
                if close:
                    db.close()


    def update_task_progress(task_id: str, progress: float, db=None):
        with _lock:
            close = False
            if db is None:
                db = SessionLocal()
                close = True
            try:
                t = db.query(Task).get(task_id)
                if not t:
                    t = Task(id=task_id)
                    db.add(t)
                t.progress = float(progress)
                db.commit()
            finally:
                if close:
                    db.close()


    def get_task(task_id: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            t = db.query(Task).get(task_id)
            if not t:
                return None
            return {
                "status": t.status,
                "result": t.result,
                "error": None,
                "progress": float(t.progress) if t.progress is not None else None,
                "fail_count": int(t.fail_count) if t.fail_count is not None else 0,
                "last_failure_ts": t.last_failure_ts.isoformat() + "Z" if t.last_failure_ts else None,
                "last_failure_error": None,
                "last_success_ts": t.last_success_ts.isoformat() + "Z" if t.last_success_ts else None,
            }
        finally:
            db.close()


else:
    import json
    import os as _os

    def _read_db() -> Dict[str, Any]:
        if not _os.path.exists(DB_PATH):
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
