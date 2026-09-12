from datetime import datetime, timezone

import pytest

from minutes.schemas import (
    STATUS_STAGE_ALIASES,
    TaskEventType,
    TaskHistoryRecord,
    TaskStage,
    build_task_event,
    is_task_stage_transition_allowed,
    task_history_record_dict,
    task_stage_from_status,
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", TaskStage.PENDING),
        (TaskStage.PENDING, TaskStage.PENDING),
        ("preprocess", TaskStage.PREPROCESS),
        ("transcribing:48.3s", TaskStage.TRANSCRIBING),
        ("formatting", TaskStage.FORMATTING),
        ("success", TaskStage.SUCCESS),
        ("failed", TaskStage.FAILED),
        ("created", TaskStage.PENDING),
        ("unknown", None),
    ],
)
def test_task_stage_from_status(status, expected):
    assert task_stage_from_status(status) == expected


@pytest.mark.parametrize("alias,stage", list(STATUS_STAGE_ALIASES.items()))
def test_status_stage_aliases(alias, stage):
    assert task_stage_from_status(alias) == stage


def test_task_history_record_dict_formats_event_ts():
    class Row:
        event_ts = datetime(2026, 8, 29, 12, 1, tzinfo=timezone.utc)
        event_type = "success"
        payload = {"result": {}}

    assert task_history_record_dict(Row()) == {
        "event_ts": "2026-08-29T12:01:00+00:00Z",
        "event_type": "success",
        "payload": {"result": {}},
    }
    missing = Row()
    missing.event_ts = None
    assert task_history_record_dict(missing)["event_ts"] is None


def test_build_status_event_adds_normalized_stage():
    event = build_task_event(
        "task-id",
        TaskEventType.STATUS,
        {"status": "transcribing:48.3s"},
    )

    assert event == {
        "type": "task.event",
        "task_id": "task-id",
        "event_type": "status",
        "stage": "transcribing",
        "payload": {"status": "transcribing", "detail": "48.3s"},
    }


def test_build_terminal_event_infers_stage():
    event = build_task_event("task-id", TaskEventType.SUCCESS, {"result": {}})

    assert event["stage"] == "success"


def test_history_record_normalizes_legacy_status_payload():
    record = TaskHistoryRecord(
        event_ts=None,
        event_type=TaskEventType.STATUS,
        payload={"status": "transcribing:48.3s"},
    )

    assert record.payload.status == TaskStage.TRANSCRIBING
    assert record.payload.detail == "48.3s"


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (TaskStage.PENDING, TaskStage.PREPROCESS, True),
        (TaskStage.PREPROCESS, TaskStage.TRANSCRIBING, True),
        (TaskStage.TRANSCRIBING, TaskStage.TRANSCRIBING, True),
        (TaskStage.TRANSCRIBING, TaskStage.FORMATTING, True),
        (TaskStage.FORMATTING, TaskStage.SUCCESS, True),
        (TaskStage.SUCCESS, TaskStage.TRANSCRIBING, False),
        (TaskStage.CANCELLED, TaskStage.SUCCESS, False),
        (TaskStage.SUCCESS, TaskStage.DELETED, True),
        (TaskStage.DELETED, TaskStage.PENDING, True),
        (TaskStage.DELETED, TaskStage.SUCCESS, True),
    ],
)
def test_task_stage_transition_contract(current, target, allowed):
    assert is_task_stage_transition_allowed(current, target) is allowed
