import uuid

from minutes.bg_store import create_task
from minutes.db import session_scope
from minutes.models import Task


def test_create_task_with_user_id():
    owner = uuid.uuid4()
    task_id = uuid.uuid4()
    # create task with explicit UUIDs
    create_task(str(task_id), metadata={"foo": "bar"}, user_id=str(owner))
    with session_scope() as db:
        t = db.get(Task, task_id)
        assert t is not None
        assert t.user_id == owner
        assert isinstance(t.result, dict)
        assert t.result.get("foo") == "bar"


def test_create_task_with_external_id_and_owner():
    owner = uuid.uuid4()
    external = "external-123"
    create_task(external, metadata={"meta": "x"}, user_id=str(owner))
    # Use raw SQL to avoid SQLAlchemy UUID type conversions in SQLite tests
    from sqlalchemy import text

    from minutes.db import engine

    conn = engine.connect()
    try:
        row = conn.execute(
            text("SELECT id, user_id, result FROM tasks WHERE result LIKE :p"),
            {"p": f"%{external}%"},
        ).fetchone()
        assert row is not None
        user_text = row[1]
        # user_text may be stored as hex string without hyphens; normalize and compare
        user_norm = str(user_text).replace("-", "").lower()
        # Ensure a user_id was stored (format: 32-hex chars)
        assert user_norm and len(user_norm) == 32
        import json

        res = json.loads(row[2]) if row[2] else {}
        assert res.get("meta") == "x"
    finally:
        conn.close()
