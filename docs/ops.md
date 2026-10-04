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
curl -sS -D - --max-time 3 http://localhost/api/bg/events -o /dev/null || true
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

## Where a change runs

Compose copies the source into an image. A file save on the host does not reach a running container. Rebuild only the services that import the changed code:

```bash
docker compose up --build -d --no-deps frontend
docker compose up --build -d --no-deps minutes
docker compose up --build -d --no-deps worker
```

- `frontend`: React UI, labels, and client-side rendering.
- `minutes`: FastAPI routes, downloads, and response shaping.
- `worker`: Whisper, the Ollama call, the prompt, and the pipeline that stores a finished task.
- A module imported by both the API and the worker, such as `minutes/pipeline/formatting.py`, needs both `minutes` and `worker` rebuilt.

Do not rebuild the whole stack for one of these changes.

## What a task stores

Whisper writes `segments` and `transcript` before formatting. Ollama's `message.content` becomes `minutes` and is also written under `data/outputs/`. `summary` and `action_items` are derived from that minutes text. `search_text` joins the task name, transcript, summary, and minutes.

The history title is filled only when the task has no name. It uses the first sentence of the output file. The minutes view reads that file. An empty file leaves the title unset and the body blank even when `segments` contain text. `result.minutes` is not a substitute for the file.

## Model differences

`OLLAMA_MODEL` selects the model for each formatting call, including a fallback model. The request adds `think: false` only when the model name contains `qwen3`. `qwen2.5` keeps the payload without that field. The minutes text is `message.content`. The thinking text is not stored.

## Checks when the screen disagrees with the code

- After a frontend rebuild, the service worker can keep the previous SPA. Unregister it in DevTools and reload. See the login note in [README.md](../README.md).
- From the host, `DATABASE_URL` uses `localhost` and the `postgresql+psycopg2://` scheme. Containers use the host name `db`. Compose builds the container URL from `POSTGRES_*` and does not read `DATABASE_URL` from `.env`.
- A successful task can still have an empty `minutes` string when Ollama returns an empty `content`. Check the worker log and the output file before treating the transcript as the minutes body.

## Local-only security

The defaults in `.env.example` are for a local portfolio demo. Docker Compose interpolates `.env` into `docker-compose.yml`; it does not load the whole file into containers. Change `ADMIN_PASS`, `JWT_SECRET`, and PostgreSQL credentials before exposing the service beyond localhost. TLS and multi-host deployment are outside the MVP scope.
