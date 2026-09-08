
- フロントエンドをデプロイ:
```bash
./scripts/deploy_frontend.sh
```

- Docker Compose でサービスを再起動:
```bash
docker compose -f docker-compose.yml -f docker-compose.minio.yml down
docker compose -f docker-compose.yml -f docker-compose.minio.yml up --build
```

- 単体テスト実行:
```bash
PYTHONPATH=. pytest -q
```

- E2E テスト実行:
```bash
pnpm run test:e2e
```



- サービス起動確認:
```bash
docker compose ps
```

- SSE エンドポイント応答確認:
```bash
curl -sS -D - http://localhost:8000/bg/events -o /dev/null
→ header に content-type: text/event-stream が含まれる。
```

- 単一インスタンステスト（ブラウザで履歴画面を開いた状態で実行）:
```bash
TASK_ID=$(curl -sS http://localhost:8000/bg/tasks | jq -r '.tasks[0].id')
curl -sS -X POST http://localhost:8000/bg/task/$TASK_ID/rename -H 'Content-Type: application/json' -d '{"name":"SSE TEST NAME"}'
```

→ ブラウザの該当タスク名／履歴が即時更新されるはず。
- クロスインスタンス（Redis 経由）テスト例（直接 Redis に publish）:
```bash
docker exec -it $(docker ps -qf name=minutes-redis) redis-cli PUBLISH minutes:events '{"type":"task.event","task_id":"<TASK_ID>","event_type":"status","payload":{"status":"transcribing"}}'
```

→ 他インスタンスのフロントにも反映されるはず。
- ログ確認:
```bash
docker compose logs -f minutes
```
