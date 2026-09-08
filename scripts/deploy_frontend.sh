#!/usr/bin/env bash
set -euo pipefail

# Build frontend and copy build output to deploy directory for nginx
# Usage: ./scripts/deploy_frontend.sh [--no-install]

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BUILD_DIR="$FRONTEND_DIR/dist"
DEPLOY_HTML_DIR="$ROOT_DIR/deploy/frontend_html"

NO_INSTALL=false
if [ "${1-}" = "--no-install" ]; then
  NO_INSTALL=true
fi

echo "Building frontend in $FRONTEND_DIR"
cd "$FRONTEND_DIR"

if [ "$NO_INSTALL" = false ]; then
  if [ -f package.json ]; then
    echo "Installing frontend dependencies (pnpm/yarn/npm)..."
    if command -v pnpm >/dev/null 2>&1; then
      pnpm install
    elif command -v yarn >/dev/null 2>&1; then
      yarn install --frozen-lockfile || yarn install
    else
      npm install
    fi
  fi
fi

echo "Running build..."
npm run build

# Ensure deploy dir exists
mkdir -p "$DEPLOY_HTML_DIR"

# Remove old files and copy new build
rm -rf "$DEPLOY_HTML_DIR"/* || true
cp -r "$BUILD_DIR"/* "$DEPLOY_HTML_DIR/"

echo "Frontend built and copied to $DEPLOY_HTML_DIR"

# When using docker-compose nginx, copy to ./frontend/dist as well for the compose volume
if [ -d "$BUILD_DIR" ]; then
  echo "Also copying build to $ROOT_DIR/frontend/dist (compose volume)"
  rm -rf "$ROOT_DIR/frontend/dist" || true
  mkdir -p "$ROOT_DIR/frontend/dist"
  # copy from deploy dir to avoid deleting the source if BUILD_DIR == frontend/dist
  cp -r "$DEPLOY_HTML_DIR"/* "$ROOT_DIR/frontend/dist/"
fi

echo "Deploy step complete."
