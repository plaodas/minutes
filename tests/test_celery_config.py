from minutes.celery_app import celery


def test_worker_imports_registered_task_module():
    assert "minutes.tasks" in celery.conf.include
    assert celery.conf.task_routes["minutes.tasks.*"]["queue"] == "minutes"
    assert celery.conf.worker_prefetch_multiplier == 1
    assert celery.conf.broker_transport_options["visibility_timeout"] == 86400


def test_process_audio_acks_after_completion():
    process_audio = celery.tasks["minutes.tasks.process_audio"]
    hard_delete = celery.tasks["minutes.tasks.hard_delete_task"]
    assert process_audio.acks_late is True
    assert process_audio.reject_on_worker_lost is True
    assert hard_delete.acks_late is False
