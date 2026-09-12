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
- `minutes`: FastAPI
- `worker`: Celery と CPU 版 faster-whisper
- `db`: PostgreSQL
- `redis`: Celery broker と SSE fan-out
- `migrate`, `bootstrap`: migration とデモユーザー作成を行う one-shot job

成果物は `data/outputs/`、アップロードは `data/uploads/` に保存します。MinIO、GPU、独立 inference service は既定の MVP 構成に含めません。

## Docker Compose で起動

必要なもの:

- Docker Engine 24 以降
- Docker Compose v2
- 初回の worker build と Whisper model download に使うインターネット接続
- CPU transcription 用に 8 GB 程度のメモリを推奨

```bash
git clone <repository-url> minutes
cd minutes

# 任意。コピーしなくてもローカルデモ用の既定値で起動できます。
cp .env.example .env

docker compose up --build -d
docker compose ps
python3 scripts/smoke_compose.py
```

ブラウザで <http://localhost:8080> を開き、次のローカル専用アカウントでログインします。

```text
username: demo
password: demo
```

認証情報や公開ポートは `.env` で変更できます。`.env.example` の値はインターネット公開環境では使用しないでください。

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

LLM 整形を確認する場合だけ `llm` profile を有効にします。指定モデルは one-shot job が自動取得します。

```bash
docker compose --profile llm up --build -d
docker compose logs -f ollama-pull
```

既定モデルは `qwen2.5:3b` です。`.env` の `OLLAMA_MODEL` で変更できます。

### 停止

```bash
docker compose down

# PostgreSQL と Ollama の named volume も消す場合
docker compose --profile llm down -v
```

## Compose の健全性確認

`scripts/smoke_compose.py` は次を frontend の公開 URL 経由で確認します。

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

Vite は `/api` を `localhost:8000` へ proxy します。

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
