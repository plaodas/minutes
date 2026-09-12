import uuid
from datetime import datetime, timezone

from sqlalchemy import event

from minutes.db import engine, session_scope
from minutes.models import Task, TaskHistory
from minutes.routers.background_task_catalog import IdList, bg_histories, bg_tasks


def test_bg_tasks_loads_history_previews_in_one_bulk_query():
    task_ids = [uuid.uuid4(), uuid.uuid4()]
    event_types = ["created", "transcribing", "formatting", "success"]
    with session_scope() as session:
        for task_id in task_ids:
            session.add(
                Task(
                    id=task_id,
                    status="success",
                    progress=100,
                    created_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
                )
            )
            for index, event_type in enumerate(event_types):
                session.add(
                    TaskHistory(
                        task_id=task_id,
                        event_type=event_type,
                        payload={"index": index},
                    )
                )

    select_statements: list[str] = []

    def record_select(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    try:
        response = bg_tasks(limit=2)
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    try:
        tasks_by_id = {task["id"]: task for task in response["tasks"]}
        for task_id in task_ids:
            task = tasks_by_id[str(task_id)]
            assert task["event_count"] == 4
            assert [
                preview["event_type"] for preview in task["preview_events"]
            ] == ["success", "formatting", "transcribing"]
        assert len(select_statements) == 2
    finally:
        with session_scope() as session:
            session.query(TaskHistory).filter(
                TaskHistory.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            session.query(Task).filter(Task.id.in_(task_ids)).delete(
                synchronize_session=False
            )


def test_bg_histories_batches_ids_in_one_query_with_individual_offsets():
    task_ids = [uuid.uuid4(), uuid.uuid4()]
    event_types = ["created", "transcribing", "formatting", "success"]
    with session_scope() as session:
        for task_id in task_ids:
            session.add(Task(id=task_id, status="success", progress=100))
            for index, event_type in enumerate(event_types):
                session.add(
                    TaskHistory(
                        task_id=task_id,
                        event_type=event_type,
                        payload={"index": index},
                    )
                )

    select_statements: list[str] = []

    def record_select(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    first_id, second_id = map(str, task_ids)
    event.listen(engine, "before_cursor_execute", record_select)
    try:
        response = bg_histories(
            IdList(
                ids=[first_id, second_id],
                limit=2,
                offsets={first_id: 0, second_id: 1},
            )
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    try:
        assert [
            item["event_type"] for item in response["histories"][first_id]
        ] == ["success", "formatting"]
        assert [
            item["event_type"] for item in response["histories"][second_id]
        ] == ["formatting", "transcribing"]
        assert len(select_statements) == 1
    finally:
        with session_scope() as session:
            session.query(TaskHistory).filter(
                TaskHistory.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            session.query(Task).filter(Task.id.in_(task_ids)).delete(
                synchronize_session=False
            )
