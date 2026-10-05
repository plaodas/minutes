import importlib.util
from pathlib import Path


def _load(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backup_writes_dump_and_copies_trees(tmp_path):
    backup = _load("backup")
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    (uploads / "meeting.mp3").write_bytes(b"audio")
    (outputs / "minutes_1.txt").write_text("body", encoding="utf-8")
    deleted = outputs / "deleted"
    deleted.mkdir()
    (deleted / "minutes_old.txt").write_text("old", encoding="utf-8")
    destination = tmp_path / "backup"

    backup.write_backup(destination, uploads, outputs, b"SQL")

    assert (destination / "db.sql").read_bytes() == b"SQL"
    assert (destination / "uploads" / "meeting.mp3").read_bytes() == b"audio"
    assert (destination / "outputs" / "deleted" / "minutes_old.txt").read_text(
        encoding="utf-8"
    ) == "old"
    assert (uploads / "meeting.mp3").exists()


def test_restore_replaces_only_given_directories(tmp_path):
    restore = _load("restore")
    source = tmp_path / "backup"
    (source / "uploads").mkdir(parents=True)
    (source / "outputs").mkdir()
    (source / "uploads" / "meeting.mp3").write_bytes(b"restored")
    (source / "outputs" / "minutes_1.txt").write_text("body", encoding="utf-8")
    (source / "db.sql").write_bytes(b"BEGIN; COMMIT;")
    uploads = tmp_path / "live-uploads"
    outputs = tmp_path / "live-outputs"
    uploads.mkdir()
    outputs.mkdir()
    (uploads / "old.mp3").write_bytes(b"old")
    calls = []

    def run(args, data=None):
        calls.append((args, data))

    restore.restore_backup(source, uploads, outputs, run)

    assert calls[0][0] == ["docker", "compose", "stop", "worker"]
    assert calls[1][0][:5] == ["docker", "compose", "exec", "-T", "db"]
    assert calls[1][1] == b"BEGIN; COMMIT;"
    assert calls[2][0] == ["docker", "compose", "start", "worker"]
    assert all("down" not in command for command, _data in calls)
    assert (uploads / "meeting.mp3").read_bytes() == b"restored"
    assert not (uploads / "old.mp3").exists()
    assert (outputs / "minutes_1.txt").read_text(encoding="utf-8") == "body"
    assert not (tmp_path / "data").exists()
