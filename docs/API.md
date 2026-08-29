# API: /bg/histories

Endpoint: `POST /bg/histories`

Summary:
- Returns recent event histories for multiple background tasks (task IDs).
- Supports per-task pagination via `offsets` map while remaining backward-compatible with the single `offset` field.

Request body (JSON):

- `ids`: string[] — list of task ids to fetch histories for.
- `limit`?: number — number of events to return per task (default server-side limit applies).
- `offset`?: number — legacy single offset applied to all `ids` (backwards compatibility).
- `offsets`?: Record<string, number> — optional per-id offset map. When present, the server uses `offsets[id]` for that id. If `offsets` is absent, the server falls back to `offset` for all ids.

Example request (per-id offsets):

```json
{
  "ids": ["task-1", "task-2"],
  "limit": 25,
  "offsets": {"task-1": 5, "task-2": 0}
}
```

Response body (JSON):

- `histories`: Record<string, Array<object>> — map from task id to an array of history events (newest-first or server-determined order).
- `hasMore`: Record<string, boolean> — whether there are more events available for a given id (useful for client-side "Load more").

Example response:

```json
{
  "histories": {
    "task-1": [
      {"event_ts":"2026-08-29T12:00:00Z","event_type":"START","payload":{}},
      {"event_ts":"2026-08-29T12:01:00Z","event_type":"PROCESS","payload":{}}
    ],
    "task-2": []
  },
  "hasMore": {"task-1": false, "task-2": false}
}
```

Notes and compatibility:
- If both `offsets` and `offset` are provided, `offsets` takes precedence for ids present in the map; `offset` is used for ids not present in the map.
- The server may enforce `BG_HISTORIES_BATCH_SIZE` to split requests into internal chunks. Clients should chunk large `ids` lists to avoid very large requests.
- This endpoint is intended to be called by the UI in a chunked, on-scroll fashion. Clients should maintain per-id counts (used as offsets) and send them in subsequent `offsets` requests when requesting more history for a specific task.

See `minutes/api.py` for the server implementation details and FastAPI schema (`IdList` model).
