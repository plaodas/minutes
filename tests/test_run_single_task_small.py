from minutes.run_single_task_small import run


def test_run_single_task_small_uses_shared_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(
        "minutes.run_single_task_small.run_audio_pipeline",
        lambda path, task_id: {
            "status": "success",
            "result": {"output_file": "/tmp/minutes.txt"},
        },
    )

    run("upload.wav", "task-1")

    assert capsys.readouterr().out.strip() == "SUCCESS /tmp/minutes.txt"


def test_run_single_task_small_prints_failure(monkeypatch, capsys):
    def fail(path, task_id):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr("minutes.run_single_task_small.run_audio_pipeline", fail)

    run("upload.wav", "task-1")

    assert capsys.readouterr().out.startswith("FAILED")
