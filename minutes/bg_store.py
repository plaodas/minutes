import os
import threading
from typing import Optional, Dict, Any

_lock = threading.Lock()

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
import uuid
from .db import SessionLocal
from .models import Task, TaskHistory
from sqlalchemy.exc import NoResultFound
from datetime import datetime
from .summary import summarize_local


def get_session():
    """Return a new DB session (caller should close it)."""
    return SessionLocal()

    def record_history(task_id: str, event_type: str, payload: dict | None = None, db=None):
        close = False
        if db is None:
            db = SessionLocal()
            close = True
        try:
            h = TaskHistory(task_id=task_id, event_type=event_type, payload=payload or {})
            db.add(h)
            db.commit()
        finally:

            def record_history(task_id: str, event_type: str, payload: dict | None = None, db=None):
                close = False
                if db is None:
                    db = SessionLocal()
                    close = True
                try:
                    h = TaskHistory(task_id=task_id, event_type=event_type, payload=payload or {})
                    db.add(h)
                    db.commit()
                finally:
                    if close:
                        db.close()


            def create_task(task_id: str, metadata: dict | None = None, db=None):
                with _lock:
                    close = False
                    if db is None:
                        db = SessionLocal()
                        close = True
                    try:
                        # Accept optional metadata (e.g. upload filename) and store
                        # it in the `result` JSON so the frontend can show upload info.
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id,
                                     status="pending", progress=None, result=metadata or None, fail_count=0)
                            db.add(t)
                        else:
                            # update result metadata if provided
                            if metadata:
                                t.result = metadata
                        db.commit()
                        try:
                            record_history(task_id, "created", {"status": "pending"}, db=db)
                        except Exception:
                            pass
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
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id)
                            db.add(t)
                        t.status = "success"
                        t.result = result
                        t.progress = 100.0
                        t.fail_count = 0
                        t.last_success_ts = datetime.utcnow()

                        # If no explicit display name exists, try to generate a short
                        # summary-based display name from the output file contents.
                        if (not getattr(t, 'name', None)) and isinstance(result, dict):
                            output_file = result.get('output_file') or (result.get('result') or {}).get('output_file')
                            if output_file:
                                outputs_dir = os.environ.get('OUTPUTS_DIR', 'outputs')
                                fname = os.path.basename(output_file)
                                candidate = os.path.join(outputs_dir, fname)
                                try:
                                    with open(candidate, 'r', encoding='utf-8') as rf:
                                        text = rf.read()
                                        # use small extractive summarizer for a short title
                                        short = summarize_local(text, max_sentences=1).strip()
                                        if short:
                                            if len(short) > 120:
                                                short = short[:117].rstrip() + '...'
                                            t.name = short
                                except Exception:
                                    pass

                        db.commit()
                        try:
                            record_history(task_id, "success", {"result": result}, db=db)
                        except Exception:
                            pass
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
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id)
                            db.add(t)
                        t.status = "failed"
                        t.result = None
                        t.fail_count = (t.fail_count or 0) + 1
                        t.last_failure_ts = datetime.utcnow()
                        db.commit()
                        try:
                            record_history(task_id, "failure", {"error": error_msg}, db=db)
                        except Exception:
                            pass
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
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id)
                            db.add(t)
                        t.status = "cancelled"
                        t.result = None
                        db.commit()
                        try:
                            record_history(task_id, "cancelled", {}, db=db)
                        except Exception:
                            pass
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
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id)
                            db.add(t)
                        t.status = status
                        db.commit()
                        try:
                            record_history(task_id, "status", {"status": status}, db=db)
                        except Exception:
                            pass
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
                        try:
                            key = uuid.UUID(task_id)
                        except Exception:
                            key = task_id
                        t = db.get(Task, key)
                        if not t:
                            t = Task(id=key if isinstance(key, uuid.UUID) else task_id)
                            db.add(t)
                        t.progress = float(progress)
                        db.commit()
                        try:
                            record_history(task_id, "progress", {"progress": float(progress)}, db=db)
                        except Exception:
                            pass
                    finally:
                        if close:
                            db.close()


            def get_task(task_id: str) -> Optional[Dict[str, Any]]:
                db = SessionLocal()
                try:
                    try:
                        key = uuid.UUID(task_id)
                    except Exception:
                        key = task_id
                    t = db.get(Task, key)
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
                        "created_at": t.created_at.isoformat() + "Z" if getattr(t, 'created_at', None) else None,
                        "name": t.name,
                    }
                finally:
                    db.close()
