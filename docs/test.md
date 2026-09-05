

サービス起動確認:
docker compose ps
SSE エンドポイント応答確認:
curl -sS -D - http://localhost:8000/bg/events -o /dev/null
→ header に content-type: text/event-stream が含まれる。
単一インスタンステスト（ブラウザで履歴画面を開いた状態で実行）:
TASK_ID=$(curl -sS http://localhost:8000/bg/tasks | jq -r '.tasks[0].id')
curl -sS -X POST http://localhost:8000/bg/task/$TASK_ID/rename -H 'Content-Type: application/json' -d '{"name":"SSE TEST NAME"}'
→ ブラウザの該当タスク名／履歴が即時更新されるはず。
クロスインスタンス（Redis 経由）テスト例（直接 Redis に publish）:
docker exec -it $(docker ps -qf name=minutes-redis) redis-cli PUBLISH minutes:events '{"type":"task.event","task_id":"<TASK_ID>","event_type":"status","payload":{"status":"transcribing"}}'
→ 他インスタンスのフロントにも反映されるはず。
ログ確認:
docker compose logs -f minutes
