#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Building frontend..."
cd frontend
if [ -f package-lock.json ] || [ -f pnpm-lock.yaml ]; then
  echo "Installing frontend deps..."
  npm ci
else
  echo "No lockfile found; skipping npm ci"
fi
npm run build

cd "$ROOT_DIR"

echo "Starting db, redis, minutes, nginx..."
docker compose up -d db redis minutes nginx

echo "Done. Visit http://localhost/ and tail logs with: docker compose logs -f nginx minutes"
