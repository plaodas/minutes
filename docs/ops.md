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
