# Test guide

## Automated checks

From the repository root, with the project virtualenv:

```bash
DATABASE_URL=sqlite:///./.pytest_fresh.db .venv/bin/python -m pytest -q
```

`tests/conftest.py` falls back to `sqlite:///./.pytest_sqlite.db` when `DATABASE_URL` is unset. That shared file keeps rows from earlier runs, so a full run should use a fresh file, as above. `python` may be absent; `.venv/bin/python` is the interpreter that has the test dependencies.

Frontend:

```bash
cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

Run the checks that cover the files you changed. A UI change also needs the affected flow exercised in a browser, not only a unit test. A Compose or image change needs the smoke test below.

## Compose smoke test

```bash
docker compose up --build -d
python3 scripts/smoke_compose.py
```

The smoke test verifies the required containers, Alembic revision, Redis, the frontend `/api` proxy, and cookie login.

## Manual end-to-end acceptance

1. Open <http://localhost> or <http://localhost:8080> and sign in with `ADMIN_USER` / `ADMIN_PASS` from `.env` (defaults: `demo` / `demo`).
2. Upload `docs/sample/demo-meeting.wav` or another short speech recording.
3. Confirm the task reaches preprocess, transcribing, formatting, and success.
4. Open the result and download its transcript, summary, and minutes.
5. Open History and confirm the same task is present.
6. Stop Ollama or omit the `llm` profile and confirm the task still succeeds with `[FALLBACK]` output.

For SSE fallback testing, enable request blocking for `/api/bg/events`, then reload so the existing EventSource is torn down. History should issue `GET /api/bg/tasks` about every 30 seconds. An in-progress upload should issue `GET /api/bg/status/{id}` about every 10 seconds. Filter Network by Fetch/XHR, not EventStream.
