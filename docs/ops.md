# Operations notes

The supported portfolio deployment is the canonical `docker-compose.yml`.

## Start and inspect

```bash
docker compose up --build -d
docker compose ps
python3 scripts/smoke_compose.py
docker compose logs -f minutes worker
```

The API and worker wait for PostgreSQL migration and demo-user bootstrap. The frontend waits for the API healthcheck.

## SSE

The browser connects to `/api/bg/events`. `frontend/nginx.conf` gives this path a dedicated unbuffered proxy with one-hour read and send timeouts.

```bash
curl -sS -D - --max-time 3 http://localhost:8080/api/bg/events -o /dev/null || true
```

The response should include `content-type: text/event-stream`. When SSE is unavailable, the frontend falls back to status polling.

## Data

- PostgreSQL uses the `pgdata` named volume.
- Uploaded files are bind-mounted at `data/uploads/`.
- Generated artifacts are bind-mounted at `data/outputs/`.
- Ollama models use the `ollama_data` named volume when the optional `llm` profile is enabled.

```bash
docker compose down
docker compose --profile llm down -v  # also remove named volumes
```

## Recovery

```bash
docker compose restart minutes worker
docker compose logs --tail 200 minutes worker db redis
docker compose run --rm migrate
docker compose run --rm bootstrap
```

Both one-shot jobs are idempotent.

## Local-only security

The defaults in `.env.example` are for a local portfolio demo. Change `ADMIN_PASS`, `JWT_SECRET`, and PostgreSQL credentials before exposing the service beyond localhost. TLS and multi-host deployment are outside the MVP scope.
