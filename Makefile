# =============================================================================
# Xulcan Developer Interface
# =============================================================================
# Usage: make [target]
# Example: make dev
# =============================================================================

.PHONY: help setup dev up down stop restart logs clean test lint shell db-shell

# === CONFIGURATION ===

COMPOSE := docker compose
# Configuration for Docker Compose profiles (e.g., --profile dev for pgadmin)
COMPOSE_ARGS := --profile dev

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