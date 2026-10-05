#!/usr/bin/env python3
"""Write a timestamped backup of PostgreSQL, uploads, and outputs.

Redis and Ollama models are not included. The queue is rebuilt by task
reclaim, and models are pulled again.
"""

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def write_backup(destination: Path, uploads: Path, outputs: Path, dump: bytes) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "db.sql").write_bytes(dump)
    _copy_tree(uploads, destination / "uploads")
    _copy_tree(outputs, destination / "outputs")


def dump_database(run=subprocess.check_output) -> bytes:
    user = os.environ.get("POSTGRES_USER", "minutes")
    database = os.environ.get("POSTGRES_DB", "minutes")
    return run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            user,
            "-d",
            database,
            "--clean",
            "--if-exists",
            "--no-owner",
        ]
    )


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
        return
    destination.mkdir(parents=True)


def main() -> None:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(os.environ.get("BACKUP_DIR", "backups"))
    destination = root / stamp
    write_backup(
        destination,
        Path(os.environ.get("UPLOADS_DIR", "data/uploads")),
        Path(os.environ.get("OUTPUTS_DIR", "data/outputs")),
        dump_database(),
    )
    print(destination)


if __name__ == "__main__":
    main()
