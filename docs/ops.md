**Worker Restart & Resilience**:

- **Restart policy**: Compose already uses `restart: unless-stopped` for services. This provides automatic restart on container crashes.

- **Wait-for dependencies**: The worker start command now invokes `scripts/wait-for-deps.sh` to wait until Redis (`redis:6379`) and Postgres (`db:5432`) are reachable before launching Celery. This prevents startup races that caused `ModuleNotFoundError`/connection errors in transient cases.

- **Manual recovery steps**:
  - Restart worker container:
    ```bash
    docker restart minutes-worker-1
    docker logs minutes-worker-1 --tail 200 -f
    ```
  - Check Redis and Postgres logs if recovery fails:
    ```bash
    docker logs minutes-redis-1 --tail 200
    docker logs minutes-db-1 --tail 200
    ```

- **Long-term fixes**:
  - Keep `restart: unless-stopped` on critical services.
  - Use `wait-for` wrappers (already added) to avoid races during startup.
  - Add monitoring/alerts for Redis and worker health.

**Nginx / SSE (Server-Sent Events)**

- **Disable buffering**: For the SSE endpoint (`/bg/events`) set `proxy_buffering off;` and `proxy_cache off;` so Nginx forwards stream data to clients immediately.
- **Use HTTP/1.1 and keepalives**: `proxy_http_version 1.1;` and `proxy_set_header Connection '';` help keep the upstream connection open.
- **Increase timeouts**: Use longer `proxy_read_timeout`/`proxy_send_timeout` (e.g. `3600s`) to allow long-lived SSE connections.
- **Cache control**: Add `Cache-Control: no-cache` on the SSE location to prevent intermediate caches from buffering.

See `deploy/nginx_minutes.conf` for a recommended configuration snippet.

**開発で nginx を使う手順**

用途: SSE 挙動、プロキシ設定、キャッシュやサブパス、TLS に近い振る舞いをローカルで検証したいときに使います。普段の高速な編集は `vite` を使い、必要なケースだけ nginx に切り替える運用がおすすめです。

手順:

- 1) フロントエンドをビルドして `frontend/dist` を作る:

```bash
cd frontend
npm ci
npm run build
```

- 2) 開発用スタックを nginx 付きで起動:

```bash
# ルートにいる前提で docker compose を使う
docker compose up -d db redis minutes nginx
```

- 3) ブラウザから確認: `http://localhost/`（`deploy/nginx_test.conf` の server_name 用にローカル環境を調整している場合はホスト名を使ってください）

- 4) SSE ヘッダ確認（nginx 経由）:

```bash
curl -sS -D - --max-time 3 http://localhost/bg/events -o /dev/null || true
```

注意点とデバッグ:

- ファイル変更のたびにフロントエンドを再ビルドする必要があります。開発中は通常は `vite`（HMR）で開発し、重要な検証のみ nginx 環境で行ってください。
- SSE が届かない場合は `deploy/nginx_test.conf` の `proxy_buffering off;`、`proxy_read_timeout`、および `add_header Cache-Control "no-cache";` を確認してください。
- ログ確認:

```bash
docker compose logs -f nginx minutes
```

- 停止/クリーンアップ:

```bash
docker compose down
```

高速な代替: nginx を立てずに `vite` と `minutes` を組み合わせて使いたい場合、`vite` のプロキシ設定で `/api` を `http://localhost:8000` に向ける方法もあります（HMR を維持しつつ API をプロキシ可能）。

このセクションは開発運用に合わせて随時更新してください。

ショートカット

- リポジトリルートに `Makefile` と `scripts/dev-nginx.sh` を追加しました。ワンコマンドでフロントエンドビルドと nginx 付きの開発スタックを起動するには:

```bash
make dev-nginx
```

`make dev-nginx` は `frontend` をビルドし、`db redis minutes nginx` を立ち上げます。
