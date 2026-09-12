# Test guide

## Automated checks

```bash
export DATABASE_URL=sqlite:///./.pytest_sqlite.db
pytest -q

cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

## Compose smoke test

```bash
docker compose up --build -d
python3 scripts/smoke_compose.py
```

The smoke test verifies the required containers, Alembic revision, Redis, the frontend `/api` proxy, and cookie login.

## Manual end-to-end acceptance

1. Open <http://localhost:8080> and sign in with the credentials from `.env`.
2. Upload a short speech recording.
3. Confirm the task reaches preprocess, transcribing, formatting, and success.
4. Open the result and download its transcript, summary, and minutes.
5. Open History and confirm the same task is present.
6. Stop Ollama or omit the `llm` profile and confirm the task still succeeds with `[FALLBACK]` output.

For SSE fallback testing, block `/api/bg/events` in browser developer tools. Status polling should still complete the active task.
