from minutes.celery_app import celery


def test_worker_imports_registered_task_module():
    assert "minutes.tasks" in celery.conf.include
    assert celery.conf.task_routes["minutes.tasks.*"]["queue"] == "minutes"
