# API: `/api/bg/histories`

正本のエンドポイントは `POST /api/bg/histories` である。OpenAPI 文書は `docs/openapi.json` にある。

接頭辞の無い `/bg/histories` は登録されていない。リクエストとレスポンスのモデルは `minutes.schemas` にある（`IdList`、`BulkTaskHistoriesResponse`、`TaskHistoryRecord`）。形の正本は OpenAPI である。

## リクエスト

JSON ボディ（`IdList`）:

- `ids`: string[] — 取得するタスク id
- `limit`?: number — タスクあたりのイベント数（既定 `1`）
- `offset`?: number — `offsets` を省略したとき、すべての id に適用する共通オフセット
- `offsets`?: Record<string, number> — id ごとのオフセット。指定があるときは `offsets[id]` を使い、マップに無い id は `0` から始まる

`offsets` と `offset` の両方があるとき、`offsets` が優先され、共通の `offset` は無視される。

```json
{
  "ids": ["task-1", "task-2"],
  "limit": 25,
  "offsets": {"task-1": 5, "task-2": 0}
}
```

## レスポンス

JSON ボディ（`BulkTaskHistoriesResponse`）:

- `histories`: Record<string, TaskHistoryRecord[]> — 要求した id ごとのイベント。新しい順。不明または不正な id は `[]` になる
- `warnings`?: string[] — サーバーが大きい `ids` を内部バッチに分割したときだけ付く

`hasMore` フィールドはない。続きのイベントが要るクライアントは、次の `offsets` を自分で送る（`offset + 返った件数`）。

```json
{
  "histories": {
    "task-1": [
      {
        "event_ts": "2026-08-29T12:01:00Z",
        "event_type": "success",
        "payload": {}
      }
    ],
    "task-2": []
  }
}
```

## 上限

- `MAX_BG_HISTORIES_IDS`（既定 500）— これを超えても処理は続く。`warnings` を足し、`ids` を `BG_HISTORIES_BATCH_SIZE`（既定 200）ずつ処理する
- `MAX_BG_HISTORIES_HARD_LIMIT`（既定 5000）— これを超えると、API は HTTP 413 と `{ "error": "..." }` を返す

実装は `minutes/routers/background_task_catalog.py` にある。
