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
