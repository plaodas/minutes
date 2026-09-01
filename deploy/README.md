Setup notes for minimal VPS deployment

1) Persistent data directories

   Create directories on the host (project root):

   ```bash
   mkdir -p data/uploads data/outputs
   chown -R $USER:$USER data
   ```

   The Docker Compose minimal mounts `./data/uploads` and `./data/outputs` into the container.

2) systemd service

   Copy `deploy/minutes.service` to `/etc/systemd/system/minutes.service` and edit the `WorkingDirectory` if needed. Then enable and start:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now minutes.service
   sudo systemctl status minutes.service
   ```

3) Nginx + Let's Encrypt

   - Install `nginx` and `certbot` (certbot-nginx or certbot with webroot). Example (Debian/Ubuntu):

     ```bash
     sudo apt update
     sudo apt install -y nginx certbot python3-certbot-nginx
     ```

   - Copy `deploy/nginx_minutes.conf` to `/etc/nginx/sites-available/minutes` and replace `example.com` with your domain. Create webroot for certbot:

     ```bash
     sudo mkdir -p /var/www/certbot
     sudo ln -s /etc/nginx/sites-available/minutes /etc/nginx/sites-enabled/minutes
     sudo nginx -t && sudo systemctl reload nginx
     ```

   - Obtain TLS certificate (uses webroot):

     ```bash
     sudo certbot certonly --webroot -w /var/www/certbot -d example.com
     ```

   - After certbot succeeds, reload nginx:

     ```bash
     sudo systemctl reload nginx
     ```

4) Notes

   - Replace `example.com` in the nginx config with your real domain.
   - Ensure ports 80/443 are open in the VPS firewall.
   - For automatic renewals, certbot installs a cron job/systemd timer by default; verify with `systemctl list-timers`.

  5) Local MinIO for development (optional)

     You can run a local MinIO instance for dev/testing. This project includes a helper compose file `docker-compose.minio.yml`.

     Quick run (one-off):

     ```bash
     # start MinIO container (data persisted under ./data/minio)
     docker run -d --name minio --restart unless-stopped \
       -p 9000:9000 -p 9001:9001 \
       -e MINIO_ROOT_USER=minioadmin \
       -e MINIO_ROOT_PASSWORD=minioadmin \
       -v "${PWD}/data/minio:/data" \
       minio/minio:latest server /data --console-address ":9001"
     ```

     Or use the compose file included in the repo:

     ```bash
     docker compose -f docker-compose.minio.yml up -d
     ```

     Environment variables (used by the app when uploading cached artifacts):

     - `MINIO_ENDPOINT` (e.g. `localhost:9000`)
     - `MINIO_ACCESS_KEY`
     - `MINIO_SECRET_KEY`
     - `MINIO_SECURE` (`true`/`false`)
     - `MINIO_DEFAULT_BUCKET` (optional bucket name to store processed minutes)

     Quick `mc` (MinIO client) examples:

     ```bash
     # configure client
     mc alias set myminio http://localhost:9000 minioadmin minioadmin

     # enable versioning on a bucket
     mc mb myminio/minutes || true
     mc version enable myminio/minutes

     # set lifecycle (example JSON file required)
     mc ilm import myminio/minutes lifecycle.json
     ```

     Notes:
     - The container uses `--restart unless-stopped` so Docker will restart it after host reboots.
     - In production consider a distributed MinIO deployment (or managed S3) with TLS, KMS, monitoring and backups; the local container is for development only.
