# 機能一覧（snapshot）

以下は現状リポジトリが提供している主要機能と振る舞い、また AI エージェントが開発の起点として必要とする実装ノートです。

## 主要機能

- 音声アップロード
  - フロントエンドの `Dropzone` から `/transcribe-upload-bg` に multipart アップロード。
  - サーバーはファイルを `uploads/` に保存し、`process_audio` Celery タスクを起動する。

- バックグラウンド処理（タスク実行）
  - タスクフロー: preprocess -> transcribe -> format
  - 実処理は `minutes/api._run_pipeline_background`（非同期/同期それぞれのラッパー）と `minutes.tasks`（Celery タスク）で実装。
  - 進捗は `minutes/bg_store.update_task_status` を通じて保存。

- 文字起こし / 推論
  - `minutes/transcribe.py` が音声からテキストを生成（内部でモデルサイズを指定）。
  - `minutes/inference_app.py` はストリーミング（NDJSON）でセグメント更新を返すエンドポイントを提供。

- 議事録フォーマット
  - `minutes/ollama.format_minutes_from_raw` が生テキストを所定のフォーマット（議事録）に変換するロジックを担う。

- タスク取得 / 結果取得 / キャンセル
  - `/bg/status/{id}`, `/bg/result/{id}`, `/bg/cancel/{id}` によりクライアントは進捗確認、結果取得、キャンセルを行える。

- オフライン/ローカル動作モード
  - `bg_store` は `DATABASE_URL` 未設定時に `data/bg_tasks.json` を使用し、ローカル検証が可能。
  - 出力は `outputs/` にファイルとして書き出される（例: minutes_*.txt）。

## 非機能要件 / 現状メモ

- 障害耐性: Celery を使用する想定だが、タスク再起動や永続ジョブ再開は限定的（reconcile_once で補助）。
- スケーラビリティ: オフロードは Celery + 外部ワーカーで拡張可能。ファイル共有ボリューム（uploads/outputs）が必要。
- セキュリティ: 現状認証・認可は未実装。`users` テーブルはあるが、アプリに組み込まれていない。

## 開発の起点メモ（AI エージェント向け）
- 新機能追加時の典型フロー:
  1. 画面コンポーネントを `frontend/src/components` に追加/更新。
  2. 必要なら新しい API を `minutes/api.py` に追加し、`minutes/schemas.py` に Pydantic スキーマを定義。
  3. サーバーサイド処理が必要なら `minutes/tasks.py` / `minutes/bg_store.py` / `minutes/models.py` を更新。
  4. DB 変更があれば Alembic マイグレーションを追加（`alembic/versions/`）。

## 優先的に取り組むと良い拡張案
- 履歴 API と永続的なユーザー設定の追加
- ダウンロード機能の signed URL 実装（ResultCards のプレースホルダを置換）
- 認証（API トークン / OAuth）とタスク所有権の紐付け
- ストリーミング transcribe の認証付きエンドポイント化
