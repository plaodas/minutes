import os
import threading
from typing import Any

_lock = threading.Lock()

import logging

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
import uuid

from .db import engine, session_scope

logger = logging.getLogger("minutes.bg_store")
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from .models import DUMMY_OWNER_ID, Bucket, Task, TaskHistory
from .schemas import TaskEventType, TaskStage, build_task_event

try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError:
    pg_insert = None
from datetime import datetime, timezone


def _now_utc() -> datetime:
    """Return a timezone-aware UTC datetime for consistency."""
    return datetime.now(tz=timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Return a tz-aware datetime (assume UTC for naive datetimes)."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        try:
            return dt.replace(tzinfo=timezone.utc)
        except (AttributeError, TypeError, ValueError):
            return dt
    return dt


from .summary import summarize_local

# SSE publisher (minimal): publish events when history rows are recorded
try:
    from .sse import publish_event
except ImportError:

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
    except (ValueError, AttributeError):
        return maybe_id


def record_history(
    task_id: str,
    event_type: str,
    payload: dict | None = None,
    emit_event: bool = True,
):
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
    try:
        with session_scope() as session:
            session.add(
                TaskHistory(
                    task_id=key,
                    event_type=event_type,
                    payload=payload or {},
                )
            )
    except SQLAlchemyError:
        logger.exception("record_history DB error for %s", task_id)
        return

    if not emit_event:
        return

    emit_task_event(task_id, event_type, payload)


def emit_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish a typed task event without requiring a history row."""
    try:
        publish_event(build_task_event(str(task_id), event_type, payload))
    except (RuntimeError, OSError):
        logger.exception("publish_event failed for %s", task_id)


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
                except (ValueError, TypeError, AttributeError):
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
                    except (AttributeError, TypeError):
                        dialect_name = None
                    if dialect_name == "postgresql":
                        try:
                            with session_scope() as s_check:
                                try:
                                    has_users_table = sa_inspect(
                                        s_check.get_bind()
                                    ).has_table("users")
                                except SQLAlchemyError:
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
                                    except SQLAlchemyError:
                                        logger.exception(
                                            "create_task: error checking user existence for %s; assuming exists",
                                            owner_val,
                                        )
                        except SQLAlchemyError:
                            logger.exception(
                                "create_task: unexpected error while checking user existence; keeping owner for %s",
                                owner_val,
                            )
                    else:
                        logger.debug(
                            "create_task: non-postgres dialect (%s); skipping user existence check",
                            dialect_name,
                        )
                except (ImportError, SQLAlchemyError, AttributeError):
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
            except AttributeError:
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
                except (SQLAlchemyError, OperationalError, AttributeError, TypeError):
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
            except SQLAlchemyError:
                logger.exception('record_history("created") failed for %s', task_id)
            logger.debug("create_task finished: task_id=%s", task_id)
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("create_task failed for %s", task_id)


def _ensure_result_bucket(session, task: Task, result: Any, task_id: str) -> None:
    if not isinstance(result, dict):
        return
    minio_info = result.get("minio") or (result.get("result") or {}).get("minio")
    if not isinstance(minio_info, dict) or not minio_info.get("bucket"):
        return

    bucket_name = str(minio_info["bucket"])
    existing = session.query(Bucket).filter(Bucket.name == bucket_name).one_or_none()
    if existing:
        return

    try:
        with session.begin_nested():
            session.add(
                Bucket(
                    name=bucket_name,
                    owner_id=getattr(task, "user_id", None) or DUMMY_OWNER_ID,
                    bucket_metadata=minio_info.get("metadata") or {},
                )
            )
            session.flush()
    except IntegrityError:
        logger.debug("Bucket row already exists for %s", bucket_name)
    except SQLAlchemyError:
        logger.exception(
            "failed to ensure bucket row for %s (task %s)", bucket_name, task_id
        )


def _get_or_create_task(session, task_id: str) -> tuple[uuid.UUID, Task] | None:
    key = _parse_key(task_id)
    if not isinstance(key, uuid.UUID):
        logger.error("Cannot create task for non-UUID id %s", task_id)
        return None

    task = session.get(Task, key)
    if task:
        return key, task

    task = Task(
        id=key,
        status="pending",
        progress=None,
        fail_count=0,
    )
    session.add(task)
    return key, task


def update_task_success(task_id: str, result: Any):
    with _lock:
        try:
            with session_scope() as s:
                resolved = _get_or_create_task(s, task_id)
                if not resolved:
                    return
                key, task = resolved

                task.status = "success"
                task.result = result
                task.progress = 100.0
                task.fail_count = 0
                task.last_success_ts = _now_utc()

                if (not getattr(task, "name", None)) and isinstance(result, dict):
                    nested_result = result.get("result")
                    output_file = result.get("output_file") or (
                        nested_result.get("output_file")
                        if isinstance(nested_result, dict)
                        else None
                    )
                    if output_file:
                        candidate = os.path.join(
                            os.environ.get("OUTPUTS_DIR", "outputs"),
                            os.path.basename(output_file),
                        )
                        try:
                            with open(candidate, "r", encoding="utf-8") as rf:
                                text = rf.read()
                                short = summarize_local(text, max_sentences=1).strip()
                                if short:
                                    title = _make_task_title(short, max_chars=20)
                                    if title:
                                        task.name = title
                        except (OSError, UnicodeDecodeError, ValueError) as exc:
                            logger.debug(
                                "update_task_success: failed to read/parse %s: %s",
                                candidate,
                                exc,
                            )

                _ensure_result_bucket(s, task, result, task_id)
                s.add(
                    TaskHistory(
                        task_id=key,
                        event_type="success",
                        payload={"result": result},
                    )
                )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_task_success failed for %s", task_id)
            return

    emit_task_event(task_id, "success", {"result": result})
    emit_task_event(task_id, TaskEventType.STATUS, {"status": "success"})


def update_task_failure(task_id: str, error_msg: str):
    with _lock:
        try:
            with session_scope() as s:
                resolved = _get_or_create_task(s, task_id)
                if not resolved:
                    return
                key, task = resolved

                task.status = "failed"
                task.result = None
                task.fail_count = (task.fail_count or 0) + 1
                task.last_failure_ts = _now_utc()
                s.add(
                    TaskHistory(
                        task_id=key,
                        event_type="failure",
                        payload={"error": error_msg},
                    )
                )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_task_failure failed for %s", task_id)
            return

    emit_task_event(task_id, "failure", {"error": error_msg})


def update_task_cancelled(task_id: str):
    with _lock:
        try:
            with session_scope() as s:
                resolved = _get_or_create_task(s, task_id)
                if not resolved:
                    return
                key, task = resolved

                task.status = "cancelled"
                task.result = None
                s.add(TaskHistory(task_id=key, event_type="cancelled", payload={}))
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_task_cancelled failed for %s", task_id)
            return

    emit_task_event(task_id, "cancelled", {})


def update_task_status(task_id: str, status: TaskStage | str):
    status_value = status.value if isinstance(status, TaskStage) else status
    with _lock:
        try:
            with session_scope() as s:
                resolved = _get_or_create_task(s, task_id)
                if not resolved:
                    return
                key, task = resolved
                task.status = status_value
                s.add(
                    TaskHistory(
                        task_id=key,
                        event_type="status",
                        payload={"status": status_value},
                    )
                )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_task_status failed for %s", task_id)
            return

    emit_task_event(task_id, TaskEventType.STATUS, {"status": status_value})


def update_task_progress(task_id: str, progress: float):
    progress_value = float(progress)
    with _lock:
        try:
            with session_scope() as s:
                resolved = _get_or_create_task(s, task_id)
                if not resolved:
                    return
                key, task = resolved
                task.progress = progress_value

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
                    except (TypeError, ValueError):
                        last_progress = None
                    if last_progress is not None:
                        delta = abs(progress_value - last_progress)
                        now = _now_utc()
                        try:
                            last_evt = _ensure_aware(last.event_ts) or now
                        except (AttributeError, TypeError, ValueError):
                            last_evt = now
                        age = (now - last_evt).total_seconds()
                        if delta < 5.0 and age < 5.0:
                            should_record = False
                if should_record:
                    now = _now_utc()
                    if last and getattr(last, "event_ts", None):
                        try:
                            last_event = _ensure_aware(last.event_ts) or now
                            last_age = (now - last_event).total_seconds()
                        except (AttributeError, TypeError, ValueError):
                            last_age = None
                    else:
                        last_age = None
                    if last and last_age is not None and last_age < 24 * 3600:
                        last.payload = {"progress": progress_value}
                        last.event_ts = now
                    else:
                        s.add(
                            TaskHistory(
                                task_id=key,
                                event_type="progress",
                                payload={"progress": progress_value},
                            )
                        )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_task_progress failed for %s", task_id)
            return

    emit_task_event(task_id, TaskEventType.PROGRESS, {"progress": progress_value})


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
