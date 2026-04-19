# Research Intelligence Agent — Docker workflows
# Usage: `make` or `make help`

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
# Rebuild only app images (api + worker); DB/Redis stay up
APP_SERVICES := api worker

.PHONY: help build build-nc up up-build up-with-web recreate recreate-app down stop restart restart-app \
	ps logs logs-api logs-worker logs-web migrate migrate-down shell-api shell-worker shell-web \
	test run-api web-install web-dev clean clean-all

help:
	@echo "Docker Compose (backend)"
	@echo ""
	@echo "  make up-build       Up in background, rebuild images if Dockerfile/app changed"
	@echo "  make recreate-app   Rebuild + force-recreate api & worker (use after code edits)"
	@echo "  make recreate       Rebuild + force-recreate all services"
	@echo "  make build / build-nc   Build images (with / without cache)"
	@echo "  make up / down / stop   Stack lifecycle"
	@echo "  make restart-app    Restart api + worker only"
	@echo "  make logs[-api|-worker] Follow logs"
	@echo "  make migrate        alembic upgrade head (inside api)"
	@echo "  make shell-api      Shell in api container"
	@echo "  make test           pytest in one-off api container"
	@echo "  make clean          docker compose down"
	@echo "  make clean-all      down + remove volumes (DB + uploads wiped)"
	@echo ""
	@echo "Frontend (web/)"
	@echo ""
	@echo "  make web-install    npm ci in web/"
	@echo "  make web-dev        Vite dev server on host (API http://localhost:8000)"
	@echo "  make up-with-web    compose up with profile web (Vite in Docker :5173)"
	@echo "  make logs-web       docker compose logs -f web (profile web)"
	@echo "  make shell-web      Shell in web container"
	@echo ""

# --- Build ---

build:
	$(COMPOSE) build

build-nc:
	$(COMPOSE) build --no-cache

# --- Run ---

up:
	$(COMPOSE) up -d

up-build:
	$(COMPOSE) up -d --build

# Backend + optional web profile (Vite at http://localhost:5173; API on host :8000)
up-with-web:
	$(COMPOSE) --profile web up -d --build

# Recreate every container (postgres/redis too) — rare
recreate:
	$(COMPOSE) up -d --build --force-recreate

# After local code changes: new image + new api/worker containers; DB/Redis usually unchanged
recreate-app:
	$(COMPOSE) build $(APP_SERVICES)
	$(COMPOSE) up -d --build --force-recreate $(APP_SERVICES)

down:
	$(COMPOSE) down

stop:
	$(COMPOSE) stop

restart:
	$(COMPOSE) restart

restart-app:
	$(COMPOSE) restart $(APP_SERVICES)

ps:
	$(COMPOSE) ps -a

# --- Logs ---

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

logs-worker:
	$(COMPOSE) logs -f worker

logs-web:
	$(COMPOSE) logs -f web

# --- Database ---

migrate:
	$(COMPOSE) exec api alembic upgrade head

migrate-down:
	$(COMPOSE) exec api alembic downgrade -1

# --- Shells & one-off ---

shell-api:
	$(COMPOSE) exec api sh

shell-worker:
	$(COMPOSE) exec worker sh

shell-web:
	$(COMPOSE) exec web sh

web-install:
	cd web && npm ci

web-dev:
	cd web && npm run dev

# Run arbitrary command in fresh api container (e.g. make run-api CMD="python -c '...'")
run-api:
	$(COMPOSE) run --rm --no-deps api $(CMD)

test:
	$(COMPOSE) run --rm --no-deps api pytest $(ARGS)

# --- Cleanup ---

clean:
	$(COMPOSE) down

clean-all:
	$(COMPOSE) down -v
	@echo "Removed volumes (postgres data + uploads)."
