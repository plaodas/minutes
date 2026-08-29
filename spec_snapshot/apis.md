# API一覧（snapshot）

このファイルはリポジトリ内の FastAPI/HTTP エンドポイントを一覧化したものです。

## サービス構成
- アプリ本体 FastAPI: `minutes/api.py`（公開 API）
- 推論用ライトウェイトサービス: `minutes/inference_app.py`
- フロントエンドが利用する API クライアント: `frontend/src/api/client.ts`

---

## 主要エンドポイント

### /health
- Method: GET
- 説明: ライフチェック。戻り値: {"status": "ok"}

### /transcribe-upload
- Method: POST
- リクエスト: multipart `file`（UploadFile）
- 説明: 同期的にアップロードを受け取り、処理を行うプロトタイプ（小ファイル向け）。
- レスポンス: `CreateTaskResponse` (task_id)

### /transcribe-upload-bg
- Method: POST
- リクエスト: multipart `file`（UploadFile）
- 説明: アップロードを受け取り、バックグラウンド処理（Celery task）として登録する。ローカルの bg store に状態を保存。
- レスポンス: `CreateTaskResponse` (task_id)

### /format-raw
- Method: POST
- リクエスト: JSON `{"raw": "..."}` (`FormatRawRequest`)
- 説明: 生テキストからフォーマット済み議事録を返す（API 経由でフォーマッタを呼び出す）。
- レスポンス: `FormatRawResponse` {"minutes": string}

### /status/{task_id}
- Method: GET
- 説明: Celery 経由のタスクステータスを返す（`celery.AsyncResult` を参照）。

### /result/{task_id}
- Method: GET
- 説明: Celery タスクの結果を返す（未完了なら 202、失敗なら 500）。

### /bg/status/{task_id}
- Method: GET
- 説明: ローカル bg store（`minutes/bg_store.py`）からタスクの状態を返す。
- レスポンス: `StatusResponse` (task_id, status, error?)

### /bg/result/{task_id}
- Method: GET
- 説明: bg store の結果を返す。成功であれば `result` を含む JSON を返す。

### /bg/cancel/{task_id}
- Method: POST
- 説明: Celery タスクの revoke/terminate を試み、ローカルストアで cancelled にマークする（ベストエフォート）。

---

## 推論向けストリーミングエンドポイント

### /transcribe (inference service)
- File: `minutes/inference_app.py`
- Method: POST
- 説明: アップロードした音声を受け取り、transcribe を別スレッドで実行して NDJSON（application/x-ndjson）でセグメント進捗と最終結果をストリームする。

---

## Pydantic スキーマ（参照）
- `minutes/schemas.py` に定義あり: `CreateTaskResponse`, `StatusResponse`, `ResultSuccess`, `FormatRawRequest`, `FormatRawResponse`。

## フロントエンドの利用
- `frontend/src/api/client.ts` が `/transcribe-upload-bg`, `/bg/status/{id}`, `/bg/result/{id}` を利用している。

---

## 実装上のメモ
- 同期エンドポイント `/transcribe-upload` は小さなファイル用のプロトタイプ。大きな/永続的な処理は Celery ベース（`process_audio` タスク）を想定。
- bg store は環境変数 `DATABASE_URL` があれば DB（SQLAlchemy）を使い、無ければ `data/bg_tasks.json` を使う。ただしプロセス再起動後の再開機能は限定的。
