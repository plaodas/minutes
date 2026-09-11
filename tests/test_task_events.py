import pytest

from minutes.schemas import (
    TaskEventType,
    TaskStage,
    build_task_event,
    task_stage_from_status,
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", TaskStage.PENDING),
        ("preprocess", TaskStage.PREPROCESS),
        ("transcribing:48.3s", TaskStage.TRANSCRIBING),
        ("formatting", TaskStage.FORMATTING),
        ("success", TaskStage.SUCCESS),
        ("failed", TaskStage.FAILED),
        ("unknown", None),
    ],
)
def test_task_stage_from_status(status, expected):
    assert task_stage_from_status(status) == expected


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
        "payload": {"status": "transcribing:48.3s"},
    }


def test_build_terminal_event_infers_stage():
    event = build_task_event("task-id", TaskEventType.SUCCESS, {"result": {}})

    assert event["stage"] == "success"
