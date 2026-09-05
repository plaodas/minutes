# Minutes — 音声から議事録を自動生成するサービス

このリポジトリは、音声ファイルを前処理して文字起こし（Whisper系）し、LLM（Ollama 等）で読みやすい議事録に整形するパイプラインとそれを提供するAPI・ワーカー群を含みます。

## 主な機能
- 音声前処理（モノラル化、正規化、WAV 出力）
- 文字起こし（`faster-whisper` を利用）
- 議事録整形（Ollama に HTTP で問い合わせ、失敗時はローカル要約でフォールバック）
- FastAPI によるアップロード API と推論用ストリーミングエンドポイント
- Celery ベースのバックグラウンドワークフロー
- MinIO を使ったオブジェクト保存サポート（オプション）

## 重要なファイル
- `run_minute_pipeline.py`, `auto_minutes_ollama.py` — ローカル実行用パイプライン
- `ollama_minutes_from_raw.py` — 既存の文字起こしから Ollama で整形
- `fw.py` — 文字起こし単体のテストスクリプト
- `minutes/` — コアモジュール（`audio.py`, `transcribe.py`, `ollama.py`, `api.py`, `tasks.py` など）
- `requirements.txt`, `requirements-api.txt` — 依存管理

## 依存と前提
- Python 3.10+ を推奨（`pyproject.toml` / `requirements*.txt` を参照）
- `ffmpeg`（音声処理）
- `faster-whisper`（ローカルで文字起こしする場合）
- Ollama サーバー（ローカルまたはホストにデプロイして HTTP 経由で利用）
- Celery とブローカー（Redis/RabbitMQ 等）を使う場合は別途セットアップ

## 環境変数（主なもの）
- `OLLAMA_HOST` — Ollama のホスト（例: `http://localhost:11434`）
- `OLLAMA_MODEL` — デフォルトで使うモデル名（例: `gemma4:e4b`）
- `OLLAMA_FALLBACK_MODELS` — カンマ区切りでフォールバックモデル
- `OUTPUTS_DIR` — 生成された議事録の出力先（デフォルト: `outputs`）
- `UPLOADS_DIR` — アップロード保存先（デフォルト: `uploads`）
- `INFERENCE_URL` — 外部推論サービスを使う場合の URL

## クイックスタート（ローカル）

1. 仮想環境を作成して依存をインストール:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-api.txt  # API を使う場合
```

2. `ffmpeg` がシステムにインストールされていることを確認。

3. 単発でローカル音声→議事録を試す:

```bash
python run_minute_pipeline.py path/to/audio.mp3
# もしくは
python auto_minutes_ollama.py path/to/audio.wav
```

生成されたファイルは `outputs/`（または `OUTPUTS_DIR`）に保存されます。

## API とワーカーの起動例

1. FastAPI アプリを起動（開発用）:

```bash
# API サーバ
uvicorn minutes.api:app --reload --port 8000

# 推論ストリーミング（独立サービス）
uvicorn minutes.inference_app:app --reload --port 9000
```

2. Celery ワーカーを起動（バックグラウンドジョブを処理する場合）:

```bash
# 環境変数で broker を設定してから実行
celery -A minutes.celery_app.celery worker --loglevel=info
```

3. Docker / docker-compose を用意している場合は、リポジトリの `docker-compose*.yml` を参照して起動できます。

## Ollama とフォールバック
`minutes/ollama.py` は Ollama に問い合わせて整形します。Ollama が利用できない場合はローカル要約器でフォールバックし、最低限の出力を返す設計になっています（可観測性のためログで警告します）。

## Case Study
このプロジェクトは、会議音声から人手の介在を減らして高速に議事録を生成することを目的としたPoC／プロダクトです。私はエンジニアリングを自らコーディングせず、プロダクトディレクションとAI活用設計を主導しました。主要な成果は以下です。

- 要件定義から運用方針まで、AI活用により短期間でプロダクト化を実現。
- `faster-whisper` を用いたローカル文字起こしと Ollama を用いた生成型整形を組み合わせ、精度と可用性のトレードオフを管理。
- Ollama が利用できないケースに備えたローカルフォールバックと可観測性（ログ／警告）を実装方針に組み込み、安定稼働を担保。
- API／ワーカーアーキテクチャ（FastAPI + Celery）を採用し、同期・非同期利用両方に対応。

### 主なインパクト（例）
- 手作業による議事録作成時間を想定で50%削減（導入先に応じて変動）
- 自動化により議事録の即時検索・配布が可能になり、会議後のフォローアップ時間を短縮

## ライセンス
- リポジトリにライセンスファイルがある場合はそちらを参照してください。

