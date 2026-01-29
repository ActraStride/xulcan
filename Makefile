# =============================================================================
# Xulcan Developer Interface
# =============================================================================
# Usage: make [target]
# Example: make dev
# =============================================================================

.PHONY: help setup dev up down stop restart logs clean test lint shell db-shell deps deps-stop uv-setup local

# === CONFIGURATION ===

COMPOSE := docker compose
# Configuration for Docker Compose profiles (e.g., --profile dev for pgadmin)
COMPOSE_ARGS := --profile dev
LOCAL_VENV ?= .venv
LOCAL_UVICORN ?= $(LOCAL_VENV)/bin/uvicorn
UV_PYTHON ?= 3.11
LOCAL_RELOAD ?= 1
LOCAL_RELOAD_FLAG := $(if $(filter 1 true yes,$(LOCAL_RELOAD)),--reload,)
LOCAL_HOST ?= 127.0.0.1

help: ## Display this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === BOOTSTRAP ===

setup: ## Configure environment (.env, secrets, and build)
	@echo "🔧 Setting up Xulcan environment..."
	@if [ ! -f .env ]; then \
		echo "📄 Creating .env from .env.example..."; \
		cp .env.example .env; \
	fi
	@bash ./scripts/setup_dev_secrets.sh
	@$(COMPOSE) build

# === LOCAL (UV) ===

deps: ## Start infra services for local runs (postgres, redis)
	@echo "🔧 Starting local dependencies..."
	@bash ./scripts/setup_dev_secrets.sh
	@$(COMPOSE) up -d postgres redis
	@echo "✅ Dependencies are running."

deps-stop: ## Stop infra services for local runs
	@$(COMPOSE) stop postgres redis

uv-setup: ## Create venv and install dev deps using uv
	@UV_BIN=$$(command -v uv || true); \
	if [ -z "$$UV_BIN" ]; then \
		echo "❌ uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	fi; \
	$$UV_BIN venv --python $(UV_PYTHON) $(LOCAL_VENV); \
	$$UV_BIN pip install -r requirements-dev.txt

local: ## Run API locally with uvicorn (requires .venv and .env)
	@if [ ! -x "$(LOCAL_UVICORN)" ]; then \
		echo "❌ Missing $(LOCAL_UVICORN). Run: make uv-setup"; \
		exit 1; \
	fi
	@if [ ! -f .env ]; then \
		echo "❌ Missing .env. Copy from .env.example and set POSTGRES_SERVER/REDIS_HOST for local."; \
		exit 1; \
	fi
	@set -a; . ./.env; set +a; \
		PYTHONPATH=app $(LOCAL_UVICORN) xulcan.main:app --host $(LOCAL_HOST) --port $${APP_PORT:-8000} $(LOCAL_RELOAD_FLAG) --log-level $${LOG_LEVEL:-info}

# === RUNTIME ===

dev: ## Start full stack (detached) and tail logs
	@$(COMPOSE) $(COMPOSE_ARGS) up -d
	@echo "🚀 Xulcan is running at http://localhost:8000"
	@echo "📜 Tailing logs (Ctrl+C to exit logs, container keeps running)..."
	@$(COMPOSE) logs -f app

up: ## Start stack in detached mode (no logs)
	@$(COMPOSE) $(COMPOSE_ARGS) up -d
	@echo "✅ Services started."

down: ## Stop and remove containers
	@$(COMPOSE) down --remove-orphans

stop: ## Stop containers without removing them
	@$(COMPOSE) stop

restart: down dev ## Restart the entire environment

logs: ## Tail application logs
	@$(COMPOSE) logs -f app

# === DEVELOPMENT TOOLS ===

test: ## Run tests (Usage: make test ARGS="-k agent")
	@echo "🧪 Running tests inside container..."
	@$(COMPOSE) exec app pytest $(ARGS)

lint: ## Run linters (Ruff/Black)
	@$(COMPOSE) exec app ruff check . --fix
	@$(COMPOSE) exec app black .

shell: ## Access app container shell
	@$(COMPOSE) exec app /bin/bash

db-shell: ## Access PostgreSQL psql console
	@$(COMPOSE) exec postgres psql -U xulcan -d xulcan_db

# === HOUSEKEEPING ===

clean: ## Destroy containers, volumes, and local cache
	@echo "🧹 Cleaning up..."
	@$(COMPOSE) --profile "*" down -v --remove-orphans
	@echo "🗑️  Removing pycache..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✨ Environment clean."
