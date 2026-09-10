# Minutes — 音声から議事録を自動生成するサービス

このリポジトリは、音声ファイルを前処理して文字起こし（ローカル Whisper 系や外部サービス）し、LLM（Ollama 等）で読みやすい議事録に整形するパイプラインとそれを提供する API・ワーカー群を含みます。

この README はコードの現状に合わせて更新しています。運用や開発で重要な変更点は「DB 設定の必須化」「短命セッションの推奨」「Celery フォーク後のエンジン破棄」です。

## 主要なポイント（現状）
- 永続的なグローバル DB セッションは避け、`minutes.db.session_scope()` を使った短命セッション（トランザクション単位）を推奨しています。
- Celery の prefork モデルでプロセスが分岐する際に、親プロセスからソケットが継承されないように `minutes.db.dispose_engine()` をワーカー初期化フックで呼び出すようになっています（`minutes.celery_app` が自動で処理します）。
- DB への接続情報は環境変数 `DATABASE_URL`（または互換名 `BG_TASK_DB_URL`）で必須にしています。開発時は SQLite の DSN を指定してローカル実行／テストが可能です。

## 主な機能
- 音声前処理（モノラル化、正規化、WAV 出力）
- 文字起こし（ローカルの `faster-whisper` 等を利用可能）
- 議事録整形（Ollama へ HTTP問い合わせ。フォールバックとしてローカル要約を利用）
- FastAPI によるアップロード API・管理 API・SSE（ライブ更新）
- Celery ベースのバックグラウンドワークフロー
- MinIO を使ったオブジェクト保存サポート（オプション）

## 重要なファイル
- `minutes/` — コアモジュール
  - `minutes/audio.py` — 前処理
  - `minutes/transcribe.py` — 文字起こしラッパ
  - `minutes/ollama.py` — Ollama問い合わせとフォールバック整形
  - `minutes/api.py` — FastAPI アプリ（エントリポイントは `backend/app.py` 経由でも起動可）
  - `minutes/inference_app.py` — 推論専用の小さな FastAPI（ストリーミングなど）
  - `minutes/tasks.py` — Celery タスク（パイプライン実装）
  - `minutes/bg_store.py` — DB によるタスクストアと履歴
  - `minutes/db.py` — SQLAlchemy エンジン、`SessionLocal`、`session_scope()`、`dispose_engine()`
  - `minutes/celery_app.py` — Celery インスタンスとワーカーフック（`dispose_engine()` 呼び出し）
- `backend/app.py` — `minutes.api:app` をラップする軽量モジュール（デプロイ/テストで使いやすい）
- `alembic/` — DB マイグレーション定義（Alembic）

## 依存と前提
- Python 3.10+ を推奨（このリポジトリでは 3.12 でも動作確認しています）
- `ffmpeg`（音声処理）
- DB: PostgreSQL 等の本番 DB（`DATABASE_URL` に DSN を指定）または開発用に SQLite（例: `sqlite:///./.pytest_sqlite.db`）
- Celery を使う場合はブローカー（Redis 等）が必要。デフォルトは `REDIS_URL=redis://redis:6379/0`。
- MinIO を使う場合は `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` 等を設定してください。
- Alembic によるマイグレーション管理を想定しています。スキーマ変更は `alembic/` を通して適用してください。

## 主な環境変数（抜粋）
- `DATABASE_URL` — DB 接続 DSN（例: `postgresql://user:pass@db:5432/minutes` または `sqlite:///./.pytest_sqlite.db`）※必須
- `BG_TASK_DB_URL` — 互換名（`DATABASE_URL` と同様に扱われます）
- `REDIS_URL` — Celery ブローカー／結果バックエンド（デフォルト: `redis://redis:6379/0`）
- `OUTPUTS_DIR` — 生成された議事録の保存先（デフォルト: `outputs`）
- `UPLOADS_DIR` — アップロード一時格納（デフォルト: `uploads`）
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_DEFAULT_BUCKET` — MinIO 設定
- `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODELS` — Ollama 関連の設定
- `ADMIN_API_TOKEN` — 管理 API 保護用のトークン（設定すると簡易認証が有効になります）

## クイックスタート（ローカル開発 / テスト）

1. 仮想環境を作成して依存をインストール:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-api.txt   # API周りの追加依存
# 開発用のツール／テスト依存が必要なら:
pip install -r requirements-dev.txt
```

2. DB 接続を指定（ローカルテスト用に SQLite を使う例）:

```bash
export DATABASE_URL="sqlite:///./.pytest_sqlite.db"
```

3. 単体でパイプラインを実行してみる:

```bash
python run_minute_pipeline.py path/to/audio.mp3
# または
python auto_minutes_ollama.py path/to/audio.wav
```

生成物は `outputs/`（または `OUTPUTS_DIR`）に保存されます。

4. API とワーカーの起動例:

```bash
# FastAPI アプリ（開発用）
uvicorn backend.app:app --reload --port 8000

# 推論ストリーミング（必要に応じて）
uvicorn minutes.inference_app:app --reload --port 9000

# Celery ワーカー（Redis 等の broker を環境変数で指定）
celery -A minutes.celery_app.celery worker --loglevel=info
```

`minutes.celery_app` はワーカー起動時に SQLAlchemy エンジンの破棄を試みるため、prefork の子プロセスで親からソケットが継承されることによる `idle in transaction` の問題が軽減されます。

5. Docker / docker-compose を使う場合:

```bash
# アプリ用 compose（例: Postgres, Redis, MinIO と連携した compose ファイルを参照）
docker compose -f docker-compose.yml -f docker-compose.minio.yml up --build

# フロントエンドをデプロイ
./scripts/deploy_frontend.sh

# Ollama のセットアップスクリプトを実行
bash setup_ollama.sh
```

## テスト実行時の注意
- テスト実行時は `DATABASE_URL` を必ず指定してください（例: `sqlite:///./.pytest_sqlite.db`）。
- テストコレクション／実行例:

```bash
export DATABASE_URL="sqlite:///./.pytest_sqlite.db"
pytest -q
```

## デザインノート（短い説明）
- DB は SQLAlchemy を用いており、セッションは `minutes.db.session_scope()` を利用してトランザクションの境界を明確にする設計です。
- `minutes.bg_store` は DB を一次ソースとしたタスクストアで、履歴は `TaskHistory` として独立した行で記録します。`maybe_session()` のように外部セッションを受け取る関数は、呼び出し元セッションを保持せず独立した短命セッションで更新を行う実装になっています。

## Ollama とフォールバック
`minutes/ollama.py` は Ollama サーバへ HTTP で問い合わせます。Ollama が利用できない場合はローカルの簡易要約器にフォールバックして最小限の出力を返すように設計されています。Ollama 関連の設定は環境変数で指定してください（`OLLAMA_HOST` 等）。

## マイグレーション
- スキーマ変更は Alembic (`alembic/`) を使って管理してください。開発環境でスキーマを反映するには Alembic の `upgrade head` を実行します。

## ライセンス
- リポジトリのルートにある `LICENSE` を参照してください。

