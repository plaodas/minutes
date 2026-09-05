import os
import threading
from typing import Optional, Dict, Any

_lock = threading.Lock()

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
import uuid
from .db import SessionLocal, engine
import logging

logger = logging.getLogger('minutes.bg_store')
from .models import Task, TaskHistory, Bucket, DUMMY_OWNER_ID
from sqlalchemy.exc import NoResultFound, IntegrityError
try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except Exception:
    pg_insert = None
from datetime import datetime
from .summary import summarize_local
import re


def _strip_markdown(text: str) -> str:
    """Remove common markdown markers and collapse whitespace."""
    if not text:
        return ""
    s = str(text)
    # remove fenced code blocks
    s = re.sub(r'```.*?```', '', s, flags=re.S)
    # inline code
    s = re.sub(r'`([^`]+)`', r'\1', s)
    # bold/italic
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)
    s = re.sub(r'\*(.*?)\*', r'\1', s)
    s = re.sub(r'__(.*?)__', r'\1', s)
    s = re.sub(r'_(.*?)_', r'\1', s)
    # links and images: keep alt/text
    s = re.sub(r'!\[(.*?)\]\([^\)]*\)', r'\1', s)
    s = re.sub(r'\[(.*?)\]\([^\)]*\)', r'\1', s)
    # remove heading markers, blockquotes, list markers at line starts
    s = re.sub(r'^[>#\-\+\*]+\s*', '', s, flags=re.M)
    # remove stray > characters
    s = re.sub(r'>\s*', '', s)
    # collapse whitespace and newlines
    s = re.sub(r'[\r\n]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _make_task_title(text: str, max_chars: int = 20) -> str:
    """Produce a short title by stripping markdown and truncating to ~max_chars."""
    s = _strip_markdown(text)
    if not s:
        return ""
    # prefer first sentence-like segment
    m = re.split(r'[\.。!?！]\s+', s, maxsplit=1)
    first = m[0].strip()
    if len(first) <= max_chars:
        return first
    # otherwise trim to nearest word under max_chars
    trimmed = first[: max_chars + 1].rstrip()
    # try to cut at last space
    if ' ' in trimmed:
        trimmed = trimmed[: trimmed.rfind(' ')].strip()
    if not trimmed:
        trimmed = first[:max_chars]
    return (trimmed[:max_chars].rstrip() + '...') if len(trimmed) >= max_chars else trimmed

# Compatibility: some modules import `DB_PATH` when file-backed fallbacks
# were used. Keep a benign default value for backward compatibility.
DB_PATH = os.environ.get('BG_TASK_DB', 'data/bg_tasks.json')


def _parse_key(maybe_id):
    """Parse and sanitize a task id into a uuid.UUID when possible.

    Some callers pass task ids with surrounding quotes, braces, or
    invisible whitespace which can lead to Postgres rejecting the value
    when cast to UUID. Return a `uuid.UUID` instance on success, or the
    original value on failure.
    """
    if isinstance(maybe_id, uuid.UUID):
        return maybe_id
    if not isinstance(maybe_id, str):
        return maybe_id
    s = maybe_id.strip()
    # strip common surrounding wrappers
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    if s.startswith('{') and s.endswith('}'):
        s = s[1:-1].strip()
    # remove non-hex/non-hyphen characters that sometimes sneak in
    cleaned = ''.join(ch for ch in s if (ch.isalnum() or ch == '-'))
    try:
        return uuid.UUID(cleaned)
    except Exception:
        return maybe_id


def get_session():
    """Return a new DB session (caller should close it)."""
    return SessionLocal()
def record_history(task_id: str, event_type: str, payload: dict | None = None, db=None):
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        logger.debug('record_history start: task_id=%s event=%s engine=%s', task_id, event_type, getattr(engine, 'url', None))
        key = _parse_key(task_id)
        # if external id isn't a UUID, _parse_key returns original string; ensure we store a UUID
        if not isinstance(key, uuid.UUID):
            # best-effort: try to find a Task row by external id in payload or skip
            # fallback: do not create history row tied to a non-UUID id
            logger.debug('record_history skipping non-UUID task_id=%s', task_id)
            return
        h = TaskHistory(task_id=key, event_type=event_type, payload=payload or {})
        db.add(h)
        try:
            db.commit()
        except Exception:
            logger.exception('record_history commit failed for %s', task_id)
            db.rollback()
    except Exception:
        logger.exception('record_history failed for %s', task_id)
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
            key = _parse_key(task_id)
            # If caller provided a UUID-like id, use it. Otherwise generate an internal UUID
            if isinstance(key, uuid.UUID):
                id_val = key
            else:
                id_val = uuid.uuid4()
                # preserve external id for traceability
                if metadata is None:
                    metadata = {}
                metadata = dict(metadata)
                metadata.setdefault('external_task_id', task_id)
            # Try PG-specific upsert to avoid race on insert. Fallback to
            # conservative get/add/commit with IntegrityError handling when
            # PG dialect isn't available.
            if pg_insert is not None:
                try:
                    logger.debug('create_task using pg_insert for %s engine=%s', task_id, getattr(engine, 'url', None))
                    stmt = pg_insert(Task.__table__).values(
                        id=id_val,
                        status="pending",
                        progress=None,
                        result=metadata or None,
                        fail_count=0,
                    ).on_conflict_do_nothing(index_elements=["id"])
                    db.execute(stmt)
                    db.commit()
                except Exception as e:
                    logger.exception('pg_insert upsert failed for %s', task_id)
                    # fallback to safe insert pattern below
                    try:
                        db.rollback()
                    except Exception:
                        logger.exception('rollback after pg_insert failed for %s', task_id)
                    t = db.get(Task, id_val)
                    if not t:
                        t = Task(id=id_val, status="pending", progress=None, result=metadata or None, fail_count=0)
                        db.add(t)
                        try:
                            db.commit()
                        except IntegrityError:
                            logger.exception('commit failed on fallback insert for %s', task_id)
                            db.rollback()
                            t = db.get(Task, id_val)
                    else:
                        if metadata:
                            t.result = metadata
                            try:
                                db.commit()
                            except IntegrityError:
                                logger.exception('commit failed updating metadata for %s', task_id)
                                db.rollback()
            else:
                t = db.get(Task, id_val)
                if not t:
                    t = Task(id=id_val, status="pending", progress=None, result=metadata or None, fail_count=0)
                    db.add(t)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        t = db.get(Task, id_val)
                else:
                    if metadata:
                        t.result = metadata
                        try:
                            db.commit()
                        except IntegrityError:
                            db.rollback()
            try:
                record_history(task_id, "created", {"status": "pending"}, db=db)
            except Exception:
                logger.exception('record_history("created") failed for %s', task_id)
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
            key = _parse_key(task_id)
            t = db.get(Task, key)
            if not t:
                # ensure task row exists atomically
                try:
                    create_task(task_id, metadata=None, db=db)
                except Exception:
                    pass
                t = db.get(Task, key)
            t.status = "success"
            t.result = result
            t.progress = 100.0
            t.fail_count = 0
            t.last_success_ts = datetime.utcnow()

            if (not getattr(t, 'name', None)) and isinstance(result, dict):
                output_file = result.get('output_file') or (result.get('result') or {}).get('output_file')
                if output_file:
                    outputs_dir = os.environ.get('OUTPUTS_DIR', 'outputs')
                    fname = os.path.basename(output_file)
                    candidate = os.path.join(outputs_dir, fname)
                    try:
                        with open(candidate, 'r', encoding='utf-8') as rf:
                            text = rf.read()
                            short = summarize_local(text, max_sentences=1).strip()
                            if short:
                                # produce a markdown-stripped short title (~20 chars)
                                title = _make_task_title(short, max_chars=20)
                                if title:
                                    t.name = title
                    except Exception:
                        pass

            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            # If the result references a MinIO cached object, ensure the bucket is recorded
            try:
                minio_info = None
                if isinstance(result, dict):
                    minio_info = result.get('minio') or (result.get('result') or {}).get('minio')
                if isinstance(minio_info, dict) and minio_info.get('bucket'):
                    bucket_name = str(minio_info.get('bucket'))
                    try:
                        existing = db.query(Bucket).filter(Bucket.name == bucket_name).one_or_none()
                        if not existing:
                            b = Bucket(name=bucket_name, owner_id=DUMMY_OWNER_ID, bucket_metadata=minio_info.get('metadata') or {})
                            db.add(b)
                            try:
                                db.commit()
                            except IntegrityError:
                                db.rollback()
                    except Exception:
                        logger.exception('failed to ensure bucket row for %s', bucket_name)
            except Exception:
                logger.exception('bucket persistence check failed for %s', task_id)
            try:
                record_history(task_id, "success", {"result": result}, db=db)
            except Exception:
                logger.exception('record_history("success") failed for %s', task_id)
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
            key = _parse_key(task_id)
            t = db.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None, db=db)
                except Exception:
                    pass
                t = db.get(Task, key)
            t.status = "failed"
            t.result = None
            t.fail_count = (t.fail_count or 0) + 1
            t.last_failure_ts = datetime.utcnow()
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            try:
                record_history(task_id, "failure", {"error": error_msg}, db=db)
            except Exception:
                logger.exception('record_history("failure") failed for %s', task_id)
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
            key = _parse_key(task_id)
            t = db.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None, db=db)
                except Exception:
                    pass
                t = db.get(Task, key)
            t.status = "cancelled"
            t.result = None
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            try:
                record_history(task_id, "cancelled", {}, db=db)
            except Exception:
                logger.exception('record_history("cancelled") failed for %s', task_id)
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
            key = _parse_key(task_id)
            t = db.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None, db=db)
                except Exception:
                    pass
                t = db.get(Task, key)
            t.status = status
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            try:
                record_history(task_id, "status", {"status": status}, db=db)
            except Exception:
                logger.exception('record_history("status") failed for %s', task_id)
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
            key = _parse_key(task_id)
            t = db.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None, db=db)
                except Exception:
                    pass
                t = db.get(Task, key)
            t.progress = float(progress)
            db.commit()
            try:
                record_history(task_id, "progress", {"progress": float(progress)}, db=db)
            except Exception:
                logger.exception('record_history("progress") failed for %s', task_id)
        finally:
            if close:
                db.close()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        key = _parse_key(task_id)
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
