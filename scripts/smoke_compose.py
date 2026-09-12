"""Verify the running portfolio Compose stack without external dependencies."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

ROOT_URL = os.environ.get("MINUTES_DEMO_URL", "http://localhost:8080").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "demo")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "demo")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "minutes")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "minutes")
REQUIRED_SERVICES = {"db", "redis", "minutes", "worker", "frontend"}


def run(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_json(opener: urllib.request.OpenerDirector, path: str) -> dict:
    with opener.open(f"{ROOT_URL}{path}", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.load(response)


def main() -> int:
    try:
        running = set(run("ps", "--status", "running", "--services").splitlines())
        missing = REQUIRED_SERVICES - running
        if missing:
            raise RuntimeError(f"services not running: {', '.join(sorted(missing))}")

        run(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-Atc",
            "SELECT version_num FROM alembic_version",
        )
        if run("exec", "-T", "redis", "redis-cli", "ping") != "PONG":
            raise RuntimeError("Redis did not return PONG")

        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        get_json(opener, "/api/health")
        login_request = urllib.request.Request(
            f"{ROOT_URL}/api/auth/login",
            data=json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login_request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"login returned HTTP {response.status}")
        features = get_json(opener, "/api/auth/features")
        if not features.get("authenticated"):
            raise RuntimeError("session cookie was not accepted")

        print("Compose smoke test passed")
        print(f"Frontend/API: {ROOT_URL}")
        print("DB migration, Redis, and demo login: OK")
        return 0
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        urllib.error.URLError,
    ) as exc:
        print(f"Compose smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
