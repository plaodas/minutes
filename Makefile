SHELL := /bin/bash

.PHONY: frontend-build frontend-deploy nginx-reload deploy-frontend
.PHONY: ci-frontend-build ci-frontend-artifact

# Build the frontend (installs deps if needed) and outputs to frontend/dist
frontend-build:
	@echo "Building frontend..."
	cd frontend && \
	if [ -f package-lock.json ] || [ -f pnpm-lock.yaml ] || [ -f yarn.lock ]; then \
	  if command -v pnpm >/dev/null 2>&1; then pnpm install; \
	  elif command -v yarn >/dev/null 2>&1; then yarn install --frozen-lockfile || yarn install; \
	  else npm install; fi; \
	fi && npm run build

# Deploy frontend build to deploy/frontend_html and frontend/dist
frontend-deploy: frontend-build
	@echo "Deploying frontend to deploy/frontend_html..."
	./scripts/deploy_frontend.sh --no-install

# Restart nginx service via docker-compose (ensure compose files used by project)
nginx-reload:
	@echo "Restarting nginx service via docker compose..."
	docker compose -f docker-compose.yml -f docker-compose.minio.yml up -d nginx

# Combined target: build, deploy to host dir, and reload nginx
deploy-frontend: frontend-deploy nginx-reload
	@echo "Frontend deployed and nginx reloaded."

# CI-friendly: install with npm ci, build, and produce a tarball artifact
ci-frontend-build:
	@echo "CI: Building frontend (npm ci + build)..."
	cd frontend && npm ci && npm run build
	@echo "CI: copying build to deploy/frontend_html"
	./scripts/deploy_frontend.sh --no-install

ci-frontend-artifact: ci-frontend-build
	@echo "CI: creating artifact artifacts/frontend_html.tar.gz"
	mkdir -p artifacts
	tar -C deploy -czf artifacts/frontend_html.tar.gz frontend_html
	@echo "CI artifact created: artifacts/frontend_html.tar.gz"
# Project Makefile

.PHONY: build
build:
	poetry build

.PHONY: dev-nginx
dev-nginx:
	./scripts/dev-nginx.sh
