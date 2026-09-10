# ruff: noqa
import os
import threading
from typing import Any

_lock = threading.Lock()

import logging

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
import uuid
from contextlib import contextmanager

from .db import engine, session_scope

logger = logging.getLogger("minutes.bg_store")
from sqlalchemy.exc import IntegrityError, OperationalError

from .models import DUMMY_OWNER_ID, Bucket, Task, TaskHistory

try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except Exception:
    pg_insert = None
from datetime import datetime

from .summary import summarize_local

# SSE publisher (minimal): publish events when history rows are recorded
try:
    from .sse import publish_event
except Exception:

    def publish_event(_):
        return


import re


def _strip_markdown(text: str) -> str:
    """Remove common markdown markers and collapse whitespace."""
    if not text:
        return ""
    s = str(text)
    # remove fenced code blocks
    s = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    # inline code
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # bold/italic
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"\*(.*?)\*", r"\1", s)
    s = re.sub(r"__(.*?)__", r"\1", s)
    s = re.sub(r"_(.*?)_", r"\1", s)
    # links and images: keep alt/text
    s = re.sub(r"!\[(.*?)\]\([^\)]*\)", r"\1", s)
    s = re.sub(r"\[(.*?)\]\([^\)]*\)", r"\1", s)
    # remove heading markers, blockquotes, list markers at line starts
    s = re.sub(r"^[>#\-\+\*]+\s*", "", s, flags=re.MULTILINE)
    # remove stray > characters
    s = re.sub(r">\s*", "", s)
    # collapse whitespace and newlines
    s = re.sub(r"[\r\n]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _make_task_title(text: str, max_chars: int = 20) -> str:
    """Produce a short title by stripping markdown and truncating to ~max_chars."""
    s = _strip_markdown(text)
    if not s:
        return ""
    # prefer first sentence-like segment
    m = re.split(r"[\.。!?！]\s+", s, maxsplit=1)
    first = m[0].strip()
    if len(first) <= max_chars:
        return first
    # otherwise trim to nearest word under max_chars
    trimmed = first[: max_chars + 1].rstrip()
    # try to cut at last space
    if " " in trimmed:
        trimmed = trimmed[: trimmed.rfind(" ")].strip()
    if not trimmed:
        trimmed = first[:max_chars]
    return (
        (trimmed[:max_chars].rstrip() + "...") if len(trimmed) >= max_chars else trimmed
    )


# Compatibility: some modules import `DB_PATH` when file-backed fallbacks
# were used. Keep a benign default value for backward compatibility.
DB_PATH = os.environ.get("BG_TASK_DB", "data/bg_tasks.json")


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
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        s = s[1:-1].strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    # remove non-hex/non-hyphen characters that sometimes sneak in
    cleaned = "".join(ch for ch in s if (ch.isalnum() or ch == "-"))
    try:
        return uuid.UUID(cleaned)
    except Exception:
        return maybe_id


@contextmanager
def maybe_session(db=None):
    """Context manager that yields (session, created_flag).

    If `db` is None, a new session is created via `session_scope()` and
    `created_flag` is True. If `db` is provided, it is yielded and
    `created_flag` is False (caller-managed session).
    """
    if db is None:
        with session_scope() as s:
            yield s, True
    else:
        try:
            yield db, False
        finally:
            pass


def record_history(task_id: str, event_type: str, payload: dict | None = None, db=None):
    try:
        logger.debug(
            "record_history start: task_id=%s event=%s engine=%s",
            task_id,
            event_type,
            getattr(engine, "url", None),
        )
        key = _parse_key(task_id)
        # if external id isn't a UUID, _parse_key returns original string; ensure we store a UUID
        if not isinstance(key, uuid.UUID):
            # best-effort: try to find a Task row by external id in payload or skip
            # fallback: do not create history row tied to a non-UUID id
            logger.debug("record_history skipping non-UUID task_id=%s", task_id)
            return
        with maybe_session(db) as (s, created):
            h = TaskHistory(task_id=key, event_type=event_type, payload=payload or {})
            s.add(h)
            try:
                s.commit()
            except Exception:
                logger.exception("record_history commit failed for %s", task_id)
                try:
                    s.rollback()
                except Exception:
                    pass
            # publish SSE event for live updates (non-blocking)
            try:
                publish_event(
                    {
                        "type": "task.event",
                        "task_id": (
                            str(key) if isinstance(key, uuid.UUID) else str(task_id)
                        ),
                        "event_type": event_type,
                        "payload": payload or {},
                    }
                )
            except Exception:
                logger.exception("publish_event failed for %s", task_id)
    except Exception:
        logger.exception("record_history failed for %s", task_id)


def create_task(
    task_id: str, metadata: dict | None = None, user_id: str | None = None, db=None
):
    with _lock:
        try:
            if db is not None:
                logger.debug(
                    "create_task: ignoring provided db session and using independent session for %s",
                    task_id,
                )
            logger.debug(
                "create_task start: task_id=%s db_provided=%s engine=%s",
                task_id,
                (db is not None),
                getattr(engine, "url", None),
            )
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
                metadata.setdefault("external_task_id", task_id)

            # Normalize user_id if provided. Only accept actual UUIDs here.
            # _parse_key may return the original string when it cannot parse;
            # avoid using non-UUID values as user_id to prevent DB cast errors
            # (which previously left transactions open).
            owner_val = None
            if user_id:
                try:
                    parsed_owner = _parse_key(user_id)
                    if isinstance(parsed_owner, uuid.UUID):
                        owner_val = parsed_owner
                    else:
                        # Not a UUID-like value; ignore the provided user_id.
                        logger.debug(
                            "create_task: ignoring non-UUID user_id=%r for task %s",
                            user_id,
                            task_id,
                        )
                        owner_val = None
                except Exception:
                    owner_val = None

            # If a user id was provided, ensure it exists in the users table
            if owner_val is not None:
                try:
                    from sqlalchemy import inspect as sa_inspect
                    from sqlalchemy import text

                    try:
                        dialect_name = (
                            getattr(engine, "dialect", None)
                            and getattr(engine.dialect, "name", "").lower()
                        )
                    except Exception:
                        dialect_name = None
                    if dialect_name == "postgresql":
                        try:
                            with session_scope() as s_check:
                                try:
                                    has_users_table = sa_inspect(
                                        s_check.get_bind()
                                    ).has_table("users")
                                except Exception:
                                    has_users_table = False
                                if has_users_table:
                                    try:
                                        res = s_check.execute(
                                            text(
                                                "SELECT 1 FROM users WHERE id = :id LIMIT 1"
                                            ),
                                            {"id": str(owner_val)},
                                        )
                                        row = (
                                            res.first()
                                            if hasattr(res, "first")
                                            else None
                                        )
                                        if not row:
                                            logger.warning(
                                                "create_task: provided user_id %s not found; clearing owner for task %s",
                                                owner_val,
                                                task_id,
                                            )
                                            owner_val = None
                                    except Exception:
                                        logger.exception(
                                            "create_task: error checking user existence for %s; assuming exists",
                                            owner_val,
                                        )
                        except Exception:
                            logger.exception(
                                "create_task: unexpected error while checking user existence; keeping owner for %s",
                                owner_val,
                            )
                    else:
                        logger.debug(
                            "create_task: non-postgres dialect (%s); skipping user existence check",
                            dialect_name,
                        )
                except Exception:
                    logger.exception(
                        "create_task: unexpected error while checking user existence; keeping owner for %s",
                        owner_val,
                    )

            # Try PG-specific upsert to avoid race on insert. Fallback to
            # conservative get/add/commit with IntegrityError handling when
            # PG dialect isn't available.
            use_pg_upsert = False
            try:
                use_pg_upsert = (
                    pg_insert is not None
                    and getattr(engine, "dialect", None)
                    and getattr(engine.dialect, "name", "").lower() == "postgresql"
                )
            except Exception:
                use_pg_upsert = False

            if use_pg_upsert:
                try:
                    logger.debug(
                        "create_task using pg_insert for %s engine=%s",
                        task_id,
                        getattr(engine, "url", None),
                    )
                    stmt = (
                        pg_insert(Task.__table__)
                        .values(
                            id=id_val,
                            status="pending",
                            progress=None,
                            result=metadata or None,
                            fail_count=0,
                            user_id=owner_val,
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                    # try once, retry on OperationalError
                    try:
                        with session_scope() as s:
                            s.execute(stmt)
                    except OperationalError:
                        logger.exception(
                            "OperationalError during pg_insert upsert for %s; retrying with fresh session",
                            task_id,
                        )
                        with session_scope() as s:
                            s.execute(stmt)
                except Exception:
                    logger.exception(
                        "pg_insert upsert failed for %s; falling back to safe insert",
                        task_id,
                    )
                    # fallback to safe insert/update
                    with session_scope() as s:
                        t = s.get(Task, id_val)
                        if not t:
                            t = Task(
                                id=id_val,
                                status="pending",
                                progress=None,
                                result=metadata or None,
                                fail_count=0,
                                user_id=owner_val,
                            )
                            s.add(t)
                        else:
                            updated = False
                            if metadata:
                                t.result = metadata
                                updated = True
                            if owner_val and not getattr(t, "user_id", None):
                                t.user_id = owner_val
                                updated = True
                            if updated:
                                s.add(t)
            else:
                with session_scope() as s:
                    t = s.get(Task, id_val)
                    if not t:
                        t = Task(
                            id=id_val,
                            status="pending",
                            progress=None,
                            result=metadata or None,
                            fail_count=0,
                            user_id=owner_val,
                        )
                        s.add(t)
                    else:
                        updated = False
                        if metadata:
                            t.result = metadata
                            updated = True
                        if owner_val and not getattr(t, "user_id", None):
                            t.user_id = owner_val
                            updated = True
                        if updated:
                            s.add(t)

            try:
                # Create history in a separate session to ensure visibility
                record_history(task_id, "created", {"status": "pending"})
            except Exception:
                logger.exception('record_history("created") failed for %s', task_id)
            logger.debug("create_task finished: task_id=%s", task_id)
        except Exception:
            logger.exception("create_task failed for %s", task_id)


def update_task_success(task_id: str, result: Any, db=None):
    with _lock:
        with maybe_session(db) as (s, created):
            try:
                key = _parse_key(task_id)
                t = s.get(Task, key)
                if not t:
                    # ensure task row exists atomically
                    try:
                        create_task(task_id, metadata=None)
                    except Exception:
                        pass
                    t = s.get(Task, key)
                t.status = "success"
                t.result = result
                t.progress = 100.0
                t.fail_count = 0
                t.last_success_ts = datetime.utcnow()

                if (not getattr(t, "name", None)) and isinstance(result, dict):
                    output_file = result.get("output_file") or (
                        result.get("result") or {}
                    ).get("output_file")
                    if output_file:
                        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
                        fname = os.path.basename(output_file)
                        candidate = os.path.join(outputs_dir, fname)
                        try:
                            with open(candidate, "r", encoding="utf-8") as rf:
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
                    s.commit()
                except IntegrityError:
                    s.rollback()
                # If the result references a MinIO cached object, ensure the bucket is recorded
                try:
                    logger.debug(
                        "update_task_success checking for minio info for task %s",
                        task_id,
                    )
                    minio_info = None
                    if isinstance(result, dict):
                        minio_info = result.get("minio") or (
                            result.get("result") or {}
                        ).get("minio")
                    if isinstance(minio_info, dict) and minio_info.get("bucket"):
                        bucket_name = str(minio_info.get("bucket"))
                        logger.info(
                            "update_task_success detected minio info for task %s: bucket=%s",
                            task_id,
                            bucket_name,
                        )
                        try:
                            existing = (
                                s.query(Bucket)
                                .filter(Bucket.name == bucket_name)
                                .one_or_none()
                            )
                            if existing:
                                logger.info(
                                    "Bucket row already exists for %s (task %s)",
                                    bucket_name,
                                    task_id,
                                )
                            else:
                                logger.info(
                                    "Inserting Bucket row for %s (task %s)",
                                    bucket_name,
                                    task_id,
                                )
                                # Prefer task.user_id as owner if available, otherwise use DUMMY_OWNER_ID
                                try:
                                    owner = (
                                        getattr(t, "user_id", None) or DUMMY_OWNER_ID
                                    )
                                except Exception:
                                    owner = DUMMY_OWNER_ID
                                b = Bucket(
                                    name=bucket_name,
                                    owner_id=owner,
                                    bucket_metadata=minio_info.get("metadata") or {},
                                )
                                s.add(b)
                                try:
                                    s.commit()
                                    logger.info(
                                        "Bucket row committed for %s (task %s)",
                                        bucket_name,
                                        task_id,
                                    )
                                except IntegrityError:
                                    logger.exception(
                                        "IntegrityError committing bucket row for %s (task %s)",
                                        bucket_name,
                                        task_id,
                                    )
                                    s.rollback()
                        except Exception:
                            logger.exception(
                                "failed to ensure bucket row for %s (task %s)",
                                bucket_name,
                                task_id,
                            )
                except Exception:
                    logger.exception("bucket persistence check failed for %s", task_id)
                try:
                    record_history(task_id, "success", {"result": result}, db=s)
                except Exception:
                    logger.exception('record_history("success") failed for %s', task_id)
                # Publish an explicit status event for frontends to consume (helps UIs
                # that listen for 'status' events to update task rows immediately).
                try:
                    publish_event(
                        {
                            "type": "task.event",
                            "task_id": (
                                str(key) if isinstance(key, uuid.UUID) else str(task_id)
                            ),
                            "event_type": "status",
                            "payload": {"status": "success"},
                        }
                    )
                except Exception:
                    logger.exception(
                        "publish_event failed for success status for %s", task_id
                    )
            except Exception:
                logger.exception("update_task_success failed for %s", task_id)


def update_task_failure(task_id: str, error_msg: str, db=None):
    with _lock, maybe_session(db) as (s, created):
        try:
            key = _parse_key(task_id)
            t = s.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None)
                except Exception:
                    pass
                t = s.get(Task, key)
            t.status = "failed"
            t.result = None
            t.fail_count = (t.fail_count or 0) + 1
            t.last_failure_ts = datetime.utcnow()
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
            try:
                record_history(task_id, "failure", {"error": error_msg}, db=s)
            except Exception:
                logger.exception('record_history("failure") failed for %s', task_id)
        except Exception:
            logger.exception("update_task_failure failed for %s", task_id)


def update_task_cancelled(task_id: str, db=None):
    with _lock, maybe_session(db) as (s, created):
        try:
            key = _parse_key(task_id)
            t = s.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None)
                except Exception:
                    pass
                t = s.get(Task, key)
            t.status = "cancelled"
            t.result = None
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
            try:
                record_history(task_id, "cancelled", {}, db=s)
            except Exception:
                logger.exception('record_history("cancelled") failed for %s', task_id)
        except Exception:
            logger.exception("update_task_cancelled failed for %s", task_id)


def update_task_status(task_id: str, status: str, db=None):
    # Use a fresh short-lived session for status updates to avoid leaving a
    # caller-provided session in an open transaction. Treat the provided `db`
    # as advisory only; we will perform the update in an independent session
    # that is committed and closed immediately.
    with _lock:
        try:
            with session_scope() as s:
                key = _parse_key(task_id)
                logger.debug(
                    "update_task_status start (isolated): task_id=%s status=%s",
                    task_id,
                    status,
                )
                try:
                    t = s.get(Task, key)
                except OperationalError:
                    logger.exception(
                        "OperationalError on s.get in update_task_status for %s",
                        task_id,
                    )
                    raise
                if not t:
                    try:
                        # create_task uses its own session and commits
                        create_task(task_id, metadata=None)
                    except Exception:
                        logger.exception(
                            "create_task failed inside update_task_status for %s",
                            task_id,
                        )
                    # re-fetch after create to get ORM object in this session
                    t = s.get(Task, key)
                t.status = status
                try:
                    s.commit()
                    logger.debug(
                        "update_task_status commit ok: task_id=%s status=%s",
                        task_id,
                        status,
                    )
                except IntegrityError:
                    s.rollback()
                    logger.exception(
                        "IntegrityError committing update_task_status for %s", task_id
                    )
        except Exception:
            logger.exception("update_task_status failed for %s", task_id)
        # Record history using an independent session to ensure visibility
        try:
            record_history(task_id, "status", {"status": status})
        except Exception:
            logger.exception('record_history("status") failed for %s', task_id)


def update_task_progress(task_id: str, progress: float, db=None):
    with _lock, maybe_session(db) as (s, created):
        try:
            key = _parse_key(task_id)
            t = s.get(Task, key)
            if not t:
                try:
                    create_task(task_id, metadata=None)
                except Exception:
                    pass
                t = s.get(Task, key)
            # Always update the Task.progress column so reads get latest value
            t.progress = float(progress)
            try:
                s.commit()
            except Exception:
                s.rollback()

            # Coalesce frequent progress updates to avoid inserting too many
            # TaskHistory rows. Only record a new progress row when either:
            # - delta >= 5.0 percentage points from the most recent progress row, or
            # - the most recent progress row is older than 5 seconds.
            try:
                last = (
                    s.query(TaskHistory)
                    .filter(
                        TaskHistory.task_id == key,
                        TaskHistory.event_type == "progress",
                    )
                    .order_by(TaskHistory.event_ts.desc())
                    .limit(1)
                    .one_or_none()
                )
                should_record = True
                if last and isinstance(last.payload, dict):
                    try:
                        last_progress = float(last.payload.get("progress", 0.0))
                    except Exception:
                        last_progress = None
                    if last_progress is not None:
                        delta = abs(float(progress) - last_progress)
                        age = (
                            datetime.utcnow() - (last.event_ts or datetime.utcnow())
                        ).total_seconds()
                        if delta < 5.0 and age < 5.0:
                            should_record = False
                if should_record:
                    # If a recent progress row exists, update it in-place to avoid
                    # accumulating many small progress INSERTs. Otherwise INSERT.
                    try:
                        recent_seconds = (
                            24 * 3600
                        )  # keep one day's worth of updates consolidated
                        last_age = (
                            (
                                datetime.utcnow() - (last.event_ts or datetime.utcnow())
                            ).total_seconds()
                            if last
                            else None
                        )
                        if last and last_age is not None and last_age < recent_seconds:
                            # update existing row
                            try:
                                last.payload = {"progress": float(progress)}
                                last.event_ts = datetime.utcnow()
                                s.add(last)
                                s.commit()
                            except Exception:
                                s.rollback()
                                # fallback to inserting a new row if update fails
                                record_history(
                                    task_id,
                                    "progress",
                                    {"progress": float(progress)},
                                    db=s,
                                )
                        else:
                            record_history(
                                task_id,
                                "progress",
                                {"progress": float(progress)},
                                db=s,
                            )
                    except Exception:
                        logger.exception(
                            "failed to upsert progress history for %s", task_id
                        )
            except Exception:
                logger.exception('record_history("progress") failed for %s', task_id)
        except Exception:
            logger.exception("update_task_progress failed for %s", task_id)


def get_task(task_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        key = _parse_key(task_id)
        t = s.get(Task, key)
        if not t:
            return None
        return {
            "status": t.status,
            "result": t.result,
            "error": None,
            "progress": float(t.progress) if t.progress is not None else None,
            "fail_count": int(t.fail_count) if t.fail_count is not None else 0,
            "last_failure_ts": (
                t.last_failure_ts.isoformat() + "Z" if t.last_failure_ts else None
            ),
            "last_failure_error": None,
            "last_success_ts": (
                t.last_success_ts.isoformat() + "Z" if t.last_success_ts else None
            ),
            "created_at": (
                t.created_at.isoformat() + "Z"
                if getattr(t, "created_at", None)
                else None
            ),
            "name": t.name,
        }
