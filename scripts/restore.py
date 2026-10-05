#!/usr/bin/env python3
"""Restore PostgreSQL, uploads, and outputs from a backup directory.

Stops the worker first and starts it again after the files are in place.
Does not remove named volumes.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
        return
    destination.mkdir(parents=True, exist_ok=True)


def restore_backup(source: Path, uploads: Path, outputs: Path, run) -> None:
    if not (source / "db.sql").is_file():
        raise FileNotFoundError(f"backup is missing db.sql: {source}")
    run(["docker", "compose", "stop", "worker"])
    replace_tree(source / "uploads", uploads)
    replace_tree(source / "outputs", outputs)
    user = os.environ.get("POSTGRES_USER", "minutes")
    database = os.environ.get("POSTGRES_DB", "minutes")
    run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
        ],
        (source / "db.sql").read_bytes(),
    )
    run(["docker", "compose", "start", "worker"])


def _run(args, data=None):
    subprocess.run(args, input=data, check=True)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: python3 scripts/restore.py <backup-directory>")
    restore_backup(
        Path(argv[1]),
        Path(os.environ.get("UPLOADS_DIR", "data/uploads")),
        Path(os.environ.get("OUTPUTS_DIR", "data/outputs")),
        _run,
    )


if __name__ == "__main__":
    main(sys.argv)
