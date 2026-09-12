# Minutes

音声ファイルをアップロードし、文字起こし、議事録整形、要約、アクション抽出を行うポートフォリオ向け Web アプリです。

## MVP で確認できること

- MP3 / WAV などの音声アップロード
- Celery worker によるバックグラウンド処理
- SSE による進捗表示と、切断時の polling fallback
- 議事録・文字起こし・要約・アクションアイテムの表示とダウンロード
- タスク履歴、名前変更、削除、キャンセル
- Cookie セッション認証

## 構成

既定の Compose は、再現に必要なサービスだけを起動します。

- `frontend`: React SPA と FastAPI への reverse proxy
- `minutes`: FastAPI（ホストへは公開しない）
- `worker`: Celery と CPU 版 faster-whisper
- `db`: PostgreSQL
- `redis`: Celery broker と SSE fan-out
- `migrate`, `bootstrap`: migration とデモユーザー作成を行う one-shot job

成果物は `data/outputs/`、アップロードは `data/uploads/` に保存します。MinIO、GPU、独立 inference service は既定の MVP 構成に含めません。

ブラウザは nginx の同一 origin から UI と `/api` の両方を取ります。Compose 経路では CORS は使いません。`localhost:8080` 用の CORS 追記は不要です。CORS 許可リストは、Vite (`http://localhost:5173`) から FastAPI へ直接叩くローカル開発向けです。

## Docker Compose で起動

必要なもの:

- Docker Engine 24 以降
- Docker Compose v2
- 初回の worker build と Whisper model download に使うインターネット接続
- CPU transcription 用に 8 GB 程度のメモリを推奨

```bash
git clone <repository-url> minutes
cd minutes

# 任意。無くても .env.example 相当の既定値で起動できます。
cp .env.example .env

docker compose up --build -d
docker compose ps
python3 scripts/smoke_compose.py
```

ブラウザで <http://localhost> または <http://localhost:8080> を開き、次のローカル専用アカウントでログインします。

```text
username: demo
password: demo
```

API は相対パス `/api` なので、開いた origin と同じホストへリクエストします。`http://localhost` なら 80 番、`http://localhost:8080` なら 8080 番です。どちらも frontend コンテナへ届きます。

ログインが `http://localhost/api/auth/login` で `ERR_CONNECTION_REFUSED` のままなら、以前登録した Service Worker が古い SPA を返していることがあります。DevTools の Application から Service Worker を Unregister して再読み込みしてください。

### `.env` の扱い

`docker compose` はプロジェクト直下の `.env` を自動で読み、`docker-compose.yml` の `${VAR}` を展開します。`env_file:` は使っていないので、ファイル全体がコンテナ環境変数になるわけではありません。参照されているキーだけが使われます。

| キー | 用途 |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | PostgreSQL と、コンテナ内 `DATABASE_URL` の組み立て |
| `JWT_SECRET` | セッション署名 |
| `ADMIN_USER`, `ADMIN_PASS` | bootstrap が作るデモユーザー |
| `FRONTEND_PORT` | 追加の公開ポート（既定 `8080`。80 番は常に公開） |
| `TRANSCRIBE_MODEL_SIZE` | worker の Whisper モデル |
| `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODELS`, `OLLAMA_TIMEOUT` | `--profile llm` のときだけ |

`.env` に残っている `MINIO_*` や `ADMIN_API_TOKEN`、`DATABASE_URL` は現行 Compose では使いません。古い MinIO 向けの値はそのままでも無視されます。ログイン ID / パスワードを変えるなら `ADMIN_USER` / `ADMIN_PASS` を `.env` に書いて `docker compose up --build -d` し直してください。

`.env.example` の値はインターネット公開環境では使用しないでください。

### 初回の音声処理

worker は最初のタスクで Whisper model を取得するため、初回だけ完了まで時間がかかります。

```bash
docker compose logs -f worker
```

短い発話入り音声をアップロードし、次を確認してください。

1. Upload が完了して task ID が表示される
2. Preprocess、Transcribing、Formatting、Complete の順に進む
3. 結果カードに transcript / summary / action items が表示される
4. History から同じタスクと成果物を開ける
5. 各成果物をダウンロードできる

Ollama を起動しない場合、整形処理は `[FALLBACK]` 付きのローカル要約へ退避します。これは正常な縮退動作です。

### Ollama を追加する

LLM 整形を確認する場合だけ `llm` profile を有効にします。`ollama-pull` が healthcheck 後にモデルを取得します。永続化先は named volume `ollama_data` です。

```bash
docker compose --profile llm up --build -d
docker compose logs -f ollama-pull
```

既定モデルは `qwen2.5:3b` です。`.env` の `OLLAMA_MODEL` で変更できます。モデル取得には数 GB の通信とディスクが必要になることがあります。

### 停止

```bash
docker compose down

# PostgreSQL と Ollama の named volume も消す場合
docker compose --profile llm down -v
```

## Compose の健全性確認

`scripts/smoke_compose.py` は frontend の公開 URL（既定 `http://localhost:8080`）経由で次を確認します。

- 必須コンテナが running
- Alembic revision が PostgreSQL に存在
- Redis が `PONG` を返す
- `/api/health` が HTTP 200
- デモユーザーでログインでき、session cookie が有効

```bash
python3 scripts/smoke_compose.py
```

URL や認証情報を変えた場合:

```bash
MINUTES_DEMO_URL=http://localhost:8081 \
ADMIN_USER=my-user \
ADMIN_PASS=my-password \
python3 scripts/smoke_compose.py
```

## ローカル開発

バックエンド:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-worker.txt -r requirements-dev.txt
pip install -e .
export DATABASE_URL=sqlite:///./.pytest_sqlite.db
uvicorn backend.app:app --reload --port 8000
```

ローカル CLI は worker と同じパイプラインを呼び出します。

```bash
minutes-cli run path/to/audio.wav
```

フロントエンド:

```bash
cd frontend
npm ci
npm run dev
```

Vite は `/api` を `localhost:8000` へ proxy します。この場合もブラウザから見た origin は Vite なので CORS は不要です。proxy を外して FastAPI へ直接 fetch する場合だけ `minutes/api.py` の CORS 許可リストが使われます。

## テスト

```bash
export DATABASE_URL=sqlite:///./.pytest_sqlite.db
pytest -q

cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

## 主要ディレクトリ

```text
minutes/
  api.py                 FastAPI composition root
  routers/               HTTP adapters
  pipeline/              preprocess / transcription / formatting / storage
  task_*.py              task lifecycle and event domain
frontend/src/
  api/                   API client and generated OpenAPI types
  events/                shared SSE provider
  hooks/                 active task and history state
  components/            UI
alembic/                  PostgreSQL migrations
scripts/                  bootstrap, schema export, smoke and maintenance tools
tests/                    backend tests
```

API の正本は `/api/...` と OpenAPI schema です。生成 TypeScript 型は次で更新します。

```bash
cd frontend
npm run generate:api-types
```

## 設計上のスコープ

この MVP は一台の Docker host での再現とデモを対象にしています。Redis outbox、GPU 対応、OAuth、TLS、MinIO の本番運用、複数 worker 間の厳密なイベント配送は対象外です。

## License

See `LICENSE`.
