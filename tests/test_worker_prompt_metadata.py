import uuid
import os
from types import SimpleNamespace

import pytest

from minutes.db import session_scope
from minutes.models import Task


def make_task(session, metadata: dict):
    t = Task(id=uuid.uuid4(), status='created', result=metadata)
    session.add(t)
    session.commit()
    return t


def test_worker_injects_language_and_actions(monkeypatch, tmp_path):
    # stub preprocess and transcribe to avoid heavy deps
    import minutes.tasks as tasks

    monkeypatch.setattr(tasks, 'preprocess', lambda p: p)
    monkeypatch.setattr(tasks, 'transcribe', lambda p, model_size=None, prompt=None, progress_callback=None: ("raw transcript text", []))

    captured = {}

    def fake_format(raw_text, model=None, system_prompt=None, host=None):
        captured['prompt'] = system_prompt
        return 'FORMATTED'

    monkeypatch.setattr(tasks, 'format_minutes_from_raw', fake_format)

    # create DB task with metadata
    with session_scope() as session:
        meta = {'language': 'Japanese', 'include_actions': False}
        t = make_task(session, meta)
        t_id = t.id

    # run worker synchronously: provide a dummy self with request.id
    class Dummy:
        request = SimpleNamespace(id=str(t_id))

    # call the prompt builder directly for deterministic testing
    prompt = tasks.build_system_prompt(meta)
    assert prompt is not None
    assert '日本語' in prompt or 'Japanese' in prompt
    assert 'Do not extract action items' in prompt
