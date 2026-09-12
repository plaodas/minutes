# API: `/api/bg/histories`

Canonical endpoint: `POST /api/bg/histories`

Unprefixed `/bg/histories` is not registered. The request and response models live in `minutes.schemas` (`IdList`, `BulkTaskHistoriesResponse`, `TaskHistoryRecord`). OpenAPI is the source of truth.

## Request

JSON body (`IdList`):

- `ids`: string[] — task ids to fetch
- `limit`?: number — events per task (default `1`)
- `offset`?: number — shared offset applied to every id when `offsets` is omitted
- `offsets`?: Record<string, number> — per-id offsets. When present, `offsets[id]` is used; ids missing from the map start at `0`

If both `offsets` and `offset` are provided, `offsets` wins and the shared `offset` is ignored.

```json
{
  "ids": ["task-1", "task-2"],
  "limit": 25,
  "offsets": {"task-1": 5, "task-2": 0}
}
```

## Response

JSON body (`BulkTaskHistoriesResponse`):

- `histories`: Record<string, TaskHistoryRecord[]> — newest-first events for each requested id. Unknown or invalid ids map to `[]`
- `warnings`?: string[] — present only when the server splits a large `ids` list into internal batches

There is no `hasMore` field. Clients that need more events send the next `offsets` themselves (`offset + returned length`).

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

## Limits

- `MAX_BG_HISTORIES_IDS` (default 500) — above this, the handler still runs but adds a `warnings` entry and processes `ids` in chunks of `BG_HISTORIES_BATCH_SIZE` (default 200)
- `MAX_BG_HISTORIES_HARD_LIMIT` (default 5000) — above this, the API returns `{ "error": "..." }` with HTTP 413

Implementation: `minutes/routers/background_task_catalog.py`.
