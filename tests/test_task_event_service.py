import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy.exc import SQLAlchemyError

from minutes import task_event_service
from minutes.task_event_service import TaskEventService


def test_record_and_publish_does_not_emit_when_commit_fails(monkeypatch):
    published = []

    class FakeSession:
        def add(self, _row):
            pass

    @contextmanager
    def failing_session_scope():
        yield FakeSession()
        raise SQLAlchemyError("commit failed")

    monkeypatch.setattr(
        task_event_service,
        "session_scope",
        failing_session_scope,
    )
    service = TaskEventService(
        lambda task_id, event_type, payload: published.append(
            (task_id, event_type, payload)
        )
    )

    with pytest.raises(SQLAlchemyError, match="commit failed"):
        service.record_and_publish(
            str(uuid.uuid4()),
            "rename",
            {"name": "Planning notes"},
        )

    assert published == []
