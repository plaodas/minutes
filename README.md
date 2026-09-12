# Minutes

会議の録音をアップロードすると、文字起こし・要約・アクションアイテム付きの議事録まで進むローカル Web アプリです。Celery worker が処理し、ブラウザは SSE（切断時は polling）で進捗を見ます。

Upload a short recording and get a transcript, summary, and action items. The default Docker Compose stack is the demo: FastAPI, a CPU Whisper worker, PostgreSQL, Redis, and an nginx frontend.

![Sign in](docs/screenshots/login.png)
![Upload workspace](docs/screenshots/upload.png)
![History](docs/screenshots/history.png)

```text
browser  →  nginx (/ and /api)
                →  FastAPI
                      →  Redis / Celery
                            →  worker (faster-whisper, optional Ollama)
```

## Quick start

```bash
git clone https://github.com/plaodas/minutes.git
cd minutes
docker compose up --build -d
python3 scripts/smoke_compose.py
```

Open <http://localhost> or <http://localhost:8080> and sign in:

```text
username: demo
password: demo
```

Upload [`docs/sample/demo-meeting.wav`](docs/sample/demo-meeting.wav). It is a short synthetic Japanese clip for the demo, not a real meeting.

The first task downloads the Whisper model and can take several minutes. Watch `docker compose logs -f worker`. Without the `llm` profile, formatting finishes with a `[FALLBACK]` local summary. That is expected.

## What the demo covers

- MP3 / WAV upload
- Background pipeline: preprocess → transcribe → format
- Live progress over SSE, with status polling if the event stream is blocked
- Transcript, summary, and action items, plus downloads
- History, rename, delete, and cancel
- Cookie session login (`demo` / `demo`)

Admin / bucket / service-token screens are out of the portfolio demo. Rebuild with `VITE_SHOW_ADMIN_CONTROLS=true` only if you need them.

## Compose services

- `frontend`: React SPA and reverse proxy to FastAPI
- `minutes`: FastAPI (not published on the host)
- `worker`: Celery and CPU faster-whisper
- `db`, `redis`
- `migrate`, `bootstrap`: Alembic and the demo user

Artifacts land in `data/outputs/`, uploads in `data/uploads/`. MinIO, GPU, and a separate inference service are not in the default stack.

Needs Docker Engine 24+, Compose v2, network for the first Whisper download, and about 8 GB RAM for CPU transcription.

If login posts to `http://localhost/api/auth/login` and fails with `ERR_CONNECTION_REFUSED`, an old Service Worker may still be serving a cached SPA. Unregister it in DevTools → Application and reload.

### `.env`

`docker compose` reads `.env` for `${VAR}` interpolation in `docker-compose.yml` only. There is no `env_file:`. Copy `.env.example` if you want to change values.

| Key | Use |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | PostgreSQL and the container `DATABASE_URL` |
| `JWT_SECRET` | Session signing |
| `ADMIN_USER`, `ADMIN_PASS` | Demo user created by bootstrap |
| `FRONTEND_PORT` | Extra host port (default `8080`; port 80 is always published) |
| `TRANSCRIBE_MODEL_SIZE` | Whisper model on the worker |
| `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODELS`, `OLLAMA_TIMEOUT` | `--profile llm` only |

`MINIO_*`, `ADMIN_API_TOKEN`, and `DATABASE_URL` in an older `.env` are ignored by this Compose file. Do not use the example secrets outside localhost.

### Optional Ollama

```bash
docker compose --profile llm up --build -d
docker compose logs -f ollama-pull
```

Default model is `qwen2.5:3b`. Models persist in the `ollama_data` volume.

### Stop

```bash
docker compose down
docker compose --profile llm down -v   # also drop named volumes
```

## Smoke test

`scripts/smoke_compose.py` checks required containers, Alembic, Redis, `/api/health`, and demo login through the frontend URL (default `http://localhost:8080`).

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

Vite proxies `/api` to `localhost:8000`, so the browser stays same-origin. CORS in `minutes/api.py` is only for talking to FastAPI directly (for example `http://localhost:5173` without the proxy). Compose nginx does not need extra CORS for `:8080`.

## Tests

```bash
export DATABASE_URL=sqlite:///./.pytest_sqlite.db
pytest -q

cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

## Layout

```text
minutes/          FastAPI composition root, routers, pipeline, task domain
frontend/src/     API client, SSE provider, hooks, UI
alembic/          PostgreSQL migrations
docs/openapi.json Generated OpenAPI schema
docs/sample/      Demo audio
scripts/          bootstrap, schema export, smoke
tests/            backend tests
```

```bash
cd frontend
npm run generate:api-types
```

This MVP targets a single Docker host. Redis outbox, GPU, OAuth, TLS, MinIO production, and strict multi-worker event delivery are out of scope.

## License

See `LICENSE`.

### 音声サンプルのクレジット
VOICEVOX:波音リツ
VOICEVOX:剣崎雌雄
