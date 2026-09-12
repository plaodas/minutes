import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import record_and_publish
from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.models import Task, TaskHistory
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    BulkTaskHistoriesResponse,
    RenameTaskRequest,
    TaskHistoryResponse,
    TaskListResponse,
    TaskNameResponse,
    task_stage_from_status,
    task_status_value,
)
from minutes.summary import summarize_local

router = APIRouter()

MAX_IDS_PER_REQUEST = int(os.environ.get("MAX_BG_HISTORIES_IDS", "500"))
HARD_IDS_LIMIT = int(os.environ.get("MAX_BG_HISTORIES_HARD_LIMIT", "5000"))
BG_HISTORIES_BATCH_SIZE = int(os.environ.get("BG_HISTORIES_BATCH_SIZE", "200"))


class IdList(BaseModel):
    ids: list[str]
    limit: int | None = 1
    offset: int | None = 0
    offsets: dict[str, int] | None = None


class _TaskNotFoundError(Exception):
    pass


class _TaskOutputUnavailableError(Exception):
    pass


@router.get(
    "/history/{task_id}",
    response_model=TaskHistoryResponse,
    response_model_exclude_none=True,
    responses={400: JSON_ERROR_RESPONSES[400]},
)
def bg_history(task_id: str, limit: int = 100, offset: int = 0):
    """Return paginated history events for a task."""
    with session_scope() as session:
        try:
            key = uuid.UUID(task_id)
        except (ValueError, TypeError):
            return error_json("invalid task id", 400)
        rows = (
            session.query(TaskHistory)
            .filter(TaskHistory.task_id == key)
            .order_by(TaskHistory.event_ts.desc())
            .offset(int(offset))
            .limit(int(limit))
            .all()
        )
        history = [
            {
                "event_ts": row.event_ts.isoformat() + "Z" if row.event_ts else None,
                "event_type": row.event_type,
                "payload": row.payload,
            }
            for row in rows
        ]
    return {"task_id": task_id, "history": history}


@router.post(
    "/task/{task_id}/rename",
    response_model=TaskNameResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        404: JSON_ERROR_RESPONSES[404],
    },
)
def bg_task_rename(task_id: str, payload: RenameTaskRequest):
    name = payload.name.strip()
    if not name:
        return error_json("missing name", 400)

    try:
        uuid.UUID(task_id)
    except (ValueError, TypeError):
        return error_json("invalid task id", 400)

    def rename_task(session, key):
        task = session.get(Task, key)
        if not task:
            raise _TaskNotFoundError
        task.name = name
        session.add(task)

    try:
        record_and_publish(
            task_id,
            "rename",
            {"name": name},
            mutate=rename_task,
        )
    except _TaskNotFoundError:
        return error_json("unknown task", 404)

    return {"task_id": task_id, "name": name}


@router.post(
    "/task/{task_id}/regenerate-name",
    response_model=TaskNameResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def bg_task_regenerate_name(task_id: str):
    try:
        uuid.UUID(task_id)
    except (ValueError, TypeError):
        return error_json("invalid task id", 400)

    def regenerate_name(session, key):
        task = session.get(Task, key)
        if not task:
            raise _TaskNotFoundError
        result = task.result or {}
        output_file = None
        if isinstance(result, dict):
            nested_result = result.get("result")
            output_file = result.get("output_file") or (
                nested_result.get("output_file")
                if isinstance(nested_result, dict)
                else None
            )
        if not output_file:
            raise _TaskOutputUnavailableError
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        candidate = os.path.join(outputs_dir, os.path.basename(output_file))
        with open(candidate, "r", encoding="utf-8") as input_file:
            text = input_file.read()
        short = summarize_local(text, max_sentences=1).strip()
        if short and len(short) > 120:
            short = short[:117].rstrip() + "..."
        task.name = short
        session.add(task)
        return short

    try:
        short = record_and_publish(
            task_id,
            "rename",
            lambda name: {"name": name},
            mutate=regenerate_name,
        )
    except _TaskNotFoundError:
        return error_json("unknown task", 404)
    except _TaskOutputUnavailableError:
        return error_json("no output file available", 404)
    except FileNotFoundError:
        return error_json("output file not found", 404)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return error_json(str(exc), 500)

    return {"task_id": task_id, "name": short}


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    response_model_exclude_none=True,
)
def bg_tasks(limit: int = 50, offset: int = 0):
    """Return a paginated task list with recent history previews."""
    with session_scope() as session:
        task_rows = (
            session.query(Task)
            .order_by(Task.created_at.desc(), Task.id.desc())
            .offset(int(offset))
            .limit(int(limit))
            .all()
        )
        previews_by_task: dict[uuid.UUID, list[dict[str, Any]]] = {
            task.id: [] for task in task_rows
        }
        counts_by_task: dict[uuid.UUID, int] = {task.id: 0 for task in task_rows}

        if task_rows:
            row_number = (
                func.row_number()
                .over(
                    partition_by=TaskHistory.task_id,
                    order_by=(
                        TaskHistory.event_ts.desc(),
                        TaskHistory.id.desc(),
                    ),
                )
                .label("rn")
            )
            event_count = (
                func.count(TaskHistory.id)
                .over(partition_by=TaskHistory.task_id)
                .label("event_count")
            )
            history_window = (
                select(
                    TaskHistory.task_id,
                    TaskHistory.event_ts,
                    TaskHistory.event_type,
                    TaskHistory.payload,
                    row_number,
                    event_count,
                )
                .where(TaskHistory.task_id.in_(list(previews_by_task)))
                .subquery()
            )
            try:
                history_rows = session.execute(
                    select(history_window)
                    .where(history_window.c.rn <= 3)
                    .order_by(history_window.c.task_id, history_window.c.rn)
                ).all()
                for row in history_rows:
                    previews_by_task[row.task_id].append(
                        {
                            "event_ts": (
                                row.event_ts.isoformat() + "Z"
                                if row.event_ts
                                else None
                            ),
                            "event_type": row.event_type,
                            "payload": row.payload,
                        }
                    )
                    counts_by_task[row.task_id] = int(row.event_count)
            except SQLAlchemyError:
                logging.getLogger(__name__).exception(
                    "failed to load task history previews"
                )

        tasks = []
        for task in task_rows:
            tasks.append(
                {
                    "id": str(task.id),
                    "name": task.name,
                    "status": task_status_value(task.status),
                    "stage": task_stage_from_status(task.status),
                    "progress": (
                        float(task.progress) if task.progress is not None else None
                    ),
                    "result": task.result,
                    "created_at": (
                        task.created_at.isoformat() + "Z" if task.created_at else None
                    ),
                    "last_success_ts": (
                        task.last_success_ts.isoformat() + "Z"
                        if task.last_success_ts
                        else None
                    ),
                    "preview_events": previews_by_task[task.id],
                    "event_count": counts_by_task[task.id],
                }
            )
    return {"tasks": tasks}


@router.post(
    "/histories",
    response_model=BulkTaskHistoriesResponse,
    response_model_exclude_none=True,
    responses={413: JSON_ERROR_RESPONSES[413]},
)
def bg_histories(payload: IdList):
    ids = payload.ids or []
    limit = int(payload.limit or 1)
    if payload.offsets:
        try:
            offsets = {str(key): int(value) for key, value in payload.offsets.items()}
        except (TypeError, ValueError):
            offsets = {}
    else:
        offset = int(payload.offset or 0)
        offsets = {task_id: offset for task_id in ids} if offset else {}
    if not ids:
        return {"histories": {}}
    if len(ids) > HARD_IDS_LIMIT:
        return error_json(
            f"too many ids in request ({len(ids)} > {HARD_IDS_LIMIT})",
            413,
        )

    warnings = []
    if len(ids) > MAX_IDS_PER_REQUEST:
        warnings.append(
            f"request contains {len(ids)} ids; processing in internal batches "
            f"of {BG_HISTORIES_BATCH_SIZE}"
        )
    histories: dict[str, list[dict[str, Any]]] = {str(task_id): [] for task_id in ids}
    with session_scope() as session:
        for start in range(0, len(ids), BG_HISTORIES_BATCH_SIZE):
            chunk = ids[start : start + BG_HISTORIES_BATCH_SIZE]
            valid_ids: dict[uuid.UUID, str] = {}
            for task_id in chunk:
                if not isinstance(task_id, str) or len(task_id) not in (32, 36):
                    continue
                try:
                    valid_ids[uuid.UUID(task_id)] = task_id
                except (ValueError, TypeError):
                    continue
            if not valid_ids:
                continue

            row_number = (
                func.row_number()
                .over(
                    partition_by=TaskHistory.task_id,
                    order_by=(
                        TaskHistory.event_ts.desc(),
                        TaskHistory.id.desc(),
                    ),
                )
                .label("rn")
            )
            subquery = (
                select(
                    TaskHistory.id,
                    TaskHistory.task_id,
                    TaskHistory.event_ts,
                    TaskHistory.event_type,
                    TaskHistory.payload,
                    row_number,
                )
                .where(TaskHistory.task_id.in_(list(valid_ids)))
                .subquery()
            )
            offset_by_task = {
                task_uuid: int(offsets.get(original_id, 0))
                for task_uuid, original_id in valid_ids.items()
            }
            task_offset = case(
                *[
                    (subquery.c.task_id == task_uuid, offset)
                    for task_uuid, offset in offset_by_task.items()
                ],
                else_=0,
            )
            query = (
                select(subquery)
                .where(subquery.c.rn > task_offset)
                .where(subquery.c.rn <= task_offset + limit)
                .order_by(subquery.c.task_id, subquery.c.rn)
            )
            for row in session.execute(query).all():
                original_id = valid_ids[row.task_id]
                histories[original_id].append(
                    {
                        "event_ts": (
                            row.event_ts.isoformat() + "Z" if row.event_ts else None
                        ),
                        "event_type": row.event_type,
                        "payload": row.payload,
                    }
                )
    response: dict[str, Any] = {"histories": histories}
    if warnings:
        response["warnings"] = warnings
    return response
