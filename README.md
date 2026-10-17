[日本語](README.ja.md)

[![CI](https://github.com/plaodas/minutes/actions/workflows/ci.yml/badge.svg)](https://github.com/plaodas/minutes/actions/workflows/ci.yml)

# Minutes

A local web app that turns a meeting recording into minutes with a transcript, summary, and action items. You can set speaker names by hand, download a Word file, and search the text of your own minutes. A Celery worker does the processing, and the browser follows progress over SSE (polling if the stream drops).

The standard Docker Compose stack is the demo. It includes FastAPI, a CPU Whisper worker, PostgreSQL, Redis, and an nginx frontend. Transcripts and minutes are isolated per logged-in user.

![Sign in](docs/screenshots/login.png)
![Upload](docs/screenshots/upload.png)
![History](docs/screenshots/history.png)

```text
browser  →  nginx (/ and /api)
                →  FastAPI
                      →  Redis / Celery
                            →  worker (faster-whisper, optional Ollama)
```

## What stays local

Recordings and minutes never leave this machine while they are processed.

- Recordings, transcripts, summaries, minutes, and accounts stay in PostgreSQL, Redis, `data/uploads/`, and `data/outputs/` inside Compose.
- Transcription runs in the worker with faster-whisper. Formatting uses Ollama on the same machine, or a local summary when Ollama is absent.
- Sign-in is a local cookie session. Nothing is sent as usage telemetry.

The only outbound traffic is the first download of each dependency.

- Docker images, the Whisper model, and the Ollama model pulled by `docker compose --profile llm` are each fetched once. Audio content is not sent after that download finishes.
- If `OLLAMA_HOST` points at another machine, formatting requests leave the local machine.
- MinIO is not part of the standard stack. If you configure it, objects are stored at that endpoint.

## Quick start

This is enough when Ollama is already running on the host. To run Ollama inside Compose, see [Optional: Ollama](#optional-ollama) below.

```bash
git clone https://github.com/plaodas/minutes.git
cd minutes
docker compose up --build -d
python3 scripts/smoke_compose.py
```

Open <http://localhost> or <http://localhost:8080> and sign in.

```text
username: demo
password: demo
```

Upload [`docs/sample/demo-meeting.wav`](docs/sample/demo-meeting.wav). It is a short synthetic Japanese clip for the demo, not a recording of a real meeting.

On a WSL2 Intel Core Ultra 5 228V (4 cores, about 16 GB RAM, no GPU), this file (2 minutes 28 seconds, 24 kHz, mono, synthetic Japanese) took about 9 minutes 30 seconds. Whisper was `medium` and formatting used `qwen3.5:4b`, both already downloaded. That time does not include the first model download.

![Minutes after processing](docs/screenshots/minutes-drawer.png)

The first task downloads the Whisper model and can take several minutes. Follow progress with `docker compose logs -f worker`. Without the `llm` profile, formatting ends as a `[FALLBACK]` local summary.

## What the demo does

- Upload MP3 / WAV
- Background processing: preprocess → transcribe → format
- Progress over SSE (status polling if the event stream is blocked)
- Minutes, summary, and action items rendered from Markdown
- Manual speaker names across selected transcript segments
- Download of text outputs and a Word minutes file with headings, an action-item table, and speaker timestamps
- Search your own history across task name, transcript, summary, and minutes body
- History, rename, delete, and cancel
- Cookie session sign-in (`demo` / `demo`)

The admin, bucket, and service-token screens are outside the portfolio demo. Rebuild with `VITE_SHOW_ADMIN_CONTROLS=true` only when you need them.

## Compose services

- `frontend`: React SPA and a reverse proxy to FastAPI
- `minutes`: FastAPI (not published on the host)
- `worker`: Celery and CPU faster-whisper
- `db`, `redis`
- `migrate`, `bootstrap`: Alembic and demo user creation

Outputs go in `data/outputs/`. Uploads go in `data/uploads/`. MinIO, a GPU, and a separate inference service are not part of the standard stack.

You need Docker Engine 24 or newer, Compose v2, network access for the first Whisper download, and about 8 GB RAM for CPU transcription.

If sign-in POSTs to `http://localhost/api/auth/login` and fails with `ERR_CONNECTION_REFUSED`, an old service worker may be serving a cached SPA. In DevTools → Application, unregister it and reload.

### `.env`

`docker compose` reads `.env` only to interpolate `${VAR}` in `docker-compose.yml`. There is no `env_file:`. Copy `.env.example` when you want to change a value.

| Key | Purpose |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | PostgreSQL and the in-container `DATABASE_URL` |
| `JWT_SECRET` | Session signing |
| `PROVISION_SECRET` | Shared secret for `POST /api/external/users`. Unset disables the endpoint. Use a value different from `JWT_SECRET` |
| `ADMIN_USER`, `ADMIN_PASS` | Demo user created by bootstrap |
| `FRONTEND_PORT` | Extra host port (default `8080`. Port 80 is always published) |
| `TRANSCRIBE_MODEL_SIZE` | Whisper model for the worker |
| `INSTALL_HAYAMIMI`, `HAYAMIMI_ENABLED` | Optional Japanese engine. Steps are in [docs/ops.md](docs/ops.md) |
| `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODELS`, `OLLAMA_TIMEOUT` | Only with `--profile llm` |

`MINIO_*`, `ADMIN_API_TOKEN`, and `DATABASE_URL` in `.env` are ignored by this Compose file. Compose builds `postgresql+psycopg2://...@db:5432/...` from `POSTGRES_*`. Use `localhost` from Python on the host, and `db` between containers. Do not use the sample secrets anywhere except localhost.

### Updating an existing install

`docker compose up --build -d` runs Alembic through the `migrate` service. To include existing tasks in history search, regenerate the search text after startup.

```bash
export DATABASE_URL=postgresql+psycopg2://minutes:minutes_password@localhost:5432/minutes
PYTHONPATH=. python scripts/backfill_search_text.py
```

If `.env` changes the PostgreSQL user, password, or database name, use those same values in the URL above. To run Alembic by hand from the host, set this `DATABASE_URL` and run `alembic upgrade head`.

### Optional: Ollama

```bash
docker compose --profile llm up --build -d
docker compose logs -f ollama-pull
```

The default model is `qwen3.5:4b`. The model stays in the `ollama_data` volume.

### Stop

```bash
docker compose down
docker compose --profile llm down -v   # also removes named volumes
```

## Smoke test

`scripts/smoke_compose.py` checks the required containers, Alembic, Redis, `/api/health`, and demo sign-in through the frontend URL (default `http://localhost:8080`).

```bash
MINUTES_DEMO_URL=http://localhost:8081 \
ADMIN_USER=my-user \
ADMIN_PASS=my-password \
python3 scripts/smoke_compose.py
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-worker.txt -r requirements-dev.txt
pip install -e .
export DATABASE_URL=sqlite:///./.pytest_sqlite.db
uvicorn backend.app:app --reload --port 8000

minutes-cli run docs/sample/demo-meeting.wav
```

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to `localhost:8000`, so the browser stays on one origin. CORS in `minutes/api.py` is for talking to FastAPI directly (for example `http://localhost:5173` with no proxy). Compose nginx does not need extra CORS for `:8080`.

## Tests

The procedure is in [docs/test.md](docs/test.md).

```bash
DATABASE_URL=sqlite:///./.pytest_fresh.db .venv/bin/python -m pytest -q

cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

## Developer docs

- [AGENTS.md](AGENTS.md): scope the coding agent follows
- [docs/ops.md](docs/ops.md): where a change is applied, what a task contains, and how to narrow a failure
- [docs/external.md](docs/external.md): user provisioning from an external service, how to call the API, and the startup order for [minutes-ext-access](https://github.com/plaodas/minutes-ext-access)
- [docs/test.md](docs/test.md): how to run tests

## Layout

```text
minutes/          FastAPI composition root, routers, pipeline, task area
frontend/src/     API client, SSE provider, hooks, UI
alembic/          PostgreSQL migrations
docs/openapi.json generated OpenAPI schema
docs/sample/      demo audio
scripts/          bootstrap, schema export, smoke test
tests/            backend tests
```

```bash
cd frontend
npm run generate:api-types
```

This MVP targets a single Docker host. A Redis outbox, GPU, OAuth, TLS, production MinIO, and strict multi-worker event delivery are out of scope.

## Related repositories

- [minutes-ext-access](https://github.com/plaodas/minutes-ext-access): Laravel sign-in that provisions a minutes user and calls this API
- [memoroku](https://github.com/plaodas/memoroku): a native phone app that records a short memo, sends it here for transcription, and shows the text on a home-screen widget

## License

See `LICENSE`.

### Audio sample credit

docs/sample/demo-meeting.wav  
VOICEVOX:波音リツ  
VOICEVOX:剣崎雌雄
