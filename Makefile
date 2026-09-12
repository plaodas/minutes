.PHONY: compose-up compose-down smoke test frontend-install frontend-test frontend-build

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

smoke:
	python3 scripts/smoke_compose.py

test:
	pytest -q

frontend-install:
	cd frontend && npm ci

frontend-test:
	cd frontend && npm run test:unit

frontend-build:
	cd frontend && npm run build
