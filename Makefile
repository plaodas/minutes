# Project Makefile

.PHONY: build
build:
	poetry build

.PHONY: dev-nginx
dev-nginx:
	./scripts/dev-nginx.sh
