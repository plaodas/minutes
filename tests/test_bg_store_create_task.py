import uuid
from minutes.bg_store import create_task
from minutes.db import SessionLocal
from minutes.models import Task


def test_create_task_with_user_id():
    owner = uuid.uuid4()
    task_id = uuid.uuid4()
    # create task with explicit UUIDs
    create_task(str(task_id), metadata={"foo": "bar"}, user_id=str(owner))
    db = SessionLocal()
    try:
        t = db.get(Task, task_id)
        assert t is not None
        assert t.user_id == owner
        assert isinstance(t.result, dict)
        assert t.result.get("foo") == "bar"
    finally:
        db.close()


def test_create_task_with_external_id_and_owner():
    owner = uuid.uuid4()
    external = "external-123"
    create_task(external, metadata={"meta": "x"}, user_id=str(owner))
    db = SessionLocal()
    try:
        # find by metadata.external_task_id
        rows = db.query(Task).all()
        match = None
        for r in rows:
            res = r.result or {}
            if isinstance(res, dict) and res.get("external_task_id") == external:
                match = r
                break
        assert match is not None
        assert match.user_id == owner
        assert match.result.get("meta") == "x"
    finally:
        db.close()
