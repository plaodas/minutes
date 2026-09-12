#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Building frontend..."
cd frontend
if [ -f package-lock.json ]; then
  echo "Installing frontend deps..."
  npm ci
else
  echo "No lockfile found; skipping npm ci"
fi
npm run build

cd "$ROOT_DIR"

echo "Starting the canonical portfolio stack..."
docker compose up --build -d

echo "Done. Visit http://localhost/ or http://localhost:8080/ and tail logs with: docker compose logs -f frontend minutes worker"
