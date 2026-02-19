# Xulcan

<p align="center">
    <a href="../README.md">English 🇬🇧</a>
    · <a href="docs/README.es.md">Spanish 🇲🇽</a>
</p>

**API-first backend framework for building AI agents with LLM orchestration, memory management, and tool execution.**

[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Enabled-blue.svg)](https://www.docker.com/)

---

## Quick Start

For an end-to-end launch + first `/orchestrate` request, see `docs/GETTING_STARTED.md`.

### Prerequisites
- Docker & Docker Compose
- Make (Standard in Linux/Mac. Windows users can use WSL2 or Git Bash)
- Python 3.11+ (recommended for local tooling)

### Setup (2 minutes)

We use a `Makefile` to standardize development tasks. No more loose scripts.

```bash
# 1. Clone the repository
git clone https://github.com/ActraStride/xulcan.git
cd xulcan

# 2. Setup environment (Generates secrets, .env, and builds images)
make setup

# 3. Start services in background
make dev

# 4. Verify installation
curl http://localhost:8000/health/live
```

### Local Development (uv, optional)

Run the API locally with `uv` while keeping Postgres/Redis in Docker.

```bash
# 1. Install uv (once)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 2. Create venv and install dependencies
make uv-setup

# 3. Create .env and set local hosts
cp .env.example .env
# Edit .env for local runs:
# ENVIRONMENT=development
# POSTGRES_SERVER=localhost
# REDIS_HOST=localhost

# 4. Start dependencies
make deps

# 5. Run the API locally
make local

# If file watching fails (permissions), disable reload:
# make local LOCAL_RELOAD=0
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://localhost:8000 | - |
| **API Docs** | http://localhost:8000/docs | - |
| **pgAdmin** | http://localhost:5050 | `admin@xulcan.dev` / (see `.secrets/pgadmin_password`) |
| **Redis Insight** | http://localhost:5540 | Configure manually on first access |

---

## Developer Interface (Make)

We provide a robust `Makefile` to handle common tasks. Run `make help` to see all commands.

| Command | Description |
|---------|-------------|
| `make setup` | Generates secrets, `.env` file, and builds Docker images. |
| `make dev` | Starts the full stack (API + DB + Tools) and tails logs. |
| `make up` | Starts the stack in detached mode (silent). |
| `make deps` | Starts only Postgres + Redis for local runs. |
| `make deps-stop` | Stops Postgres + Redis started by `make deps`. |
| `make uv-setup` | Creates a local venv and installs dev deps via uv. |
| `make local` | Runs the API locally with uvicorn (uses `.env`). |
| `make stop` | Stops containers without removing them. |
| `make clean` | **Destructive**. Removes containers, volumes, and local cache. |
| `make test` | Runs the pytest suite inside the container. |
| `make shell` | Opens a bash shell inside the API container. |
| `make db-shell`| Opens a `psql` session directly to the database. |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Application                 │
│                                                         │
│  • REST API (Universal Executor)                        │
│  • Health checks (/health/live)                         │
│  • Structured logging (JSON/Console)                    │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌─────────▼───────┐
│   PostgreSQL   │    │      Redis      │
│ (Vectors/Data) │    │ (Cache/Queue)   │
└────────────────┘    └─────────────────┘
```

### Core Components

- **FastAPI**: Async REST API with automatic OpenAPI docs.
- **PostgreSQL**: Primary data store. Will support `pgvector` for RAG.
- **Redis**: High-performance caching, rate limiting, and task queue broker.
- **Arq**: (Planned) Async job queue built on Redis for background agent reasoning.
- **Docker Secrets**: Secure credential management for production-grade security.

---

## Configuration

### Environment Variables

Configuration is managed via `.env` file (created automatically by `make setup`) and Docker Secrets.

```bash
# Application
ENVIRONMENT=development
LOG_LEVEL=debug

# Database & Redis
POSTGRES_USER=xulcan
POSTGRES_DB=xulcan_db
POSTGRES_SERVER=postgres
REDIS_HOST=redis
REDIS_PORT=6379

# AI Providers (Get your own keys)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Secrets Management

Sensitive passwords are **never** stored in environment variables. They are managed via files in `.secrets/` mounted directly into containers.

To regenerate secrets (e.g., if you forgot the pgAdmin password):

```bash
# Warning: This overwrites existing secrets
rm .secrets/*
make setup
```

---

## Project Structure

```
xulcan/
├── app/
│   └── xulcan/
│       ├── main.py              # Application entry point
│       ├── config.py            # Pydantic settings
│       └── core/                # Core logic
├── scripts/
│   └── setup_dev_secrets.sh     # Secret generation logic
├── tests/                       # Pytest suite
├── docker-compose.yaml          # Orchestration
├── Makefile                     # Developer Task Runner
├── pytest.ini                   # Test configuration
└── README.md
```

---

## Deployment

### Production Checklist

- [ ] Set `ENVIRONMENT=production` in `.env`.
- [ ] Use `make setup` on the server to generate unique secrets.
- [ ] Set strict firewall rules for Redis and Postgres ports.
- [ ] Configure a reverse proxy (Nginx/Traefik) with SSL.
- [ ] Use an external Secret Manager (like Infisical) for API Keys.

### Docker Production Build

```bash
# Build production image
docker build -t xulcan-api:latest .

# Run with production secrets
docker run -d \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  --secret postgres_password \
  --secret redis_password \
  xulcan-api:latest
```

---

## Roadmap

### ✅ Completed
- Base infrastructure (Docker, Postgres, Redis).
- **Developer Experience**: Makefile, Healthchecks, Hot-reload.
- Security: Docker Secrets, non-root containers.
- Development tools: pgAdmin, Redis Insight.

### 🚧 In Progress (Q1 2025)
- **Universal Executor**: No-code tool execution engine.
- **Agent Registry**: Database schema for defining agents via JSON/YAML.
- **Auth Gateway**: Integration with Vault/Infisical for tool authentication.

### 📋 Planned (Q2 2025)
- **RAG Integration**: Native `pgvector` support.
- **Async Reasoning**: Background workers using **Arq**.
- **Admin Dashboard**: Web UI to manage agents and view metrics.

---

## Troubleshooting

### Services behave unexpectedly
Run a full clean restart to ensure no stale volumes exist:
```bash
make clean
make setup
make dev
```

### "Redis is unhealthy"
Ensure you ran `make setup` to generate the `.secrets/redis_password` file. The container requires this file to pass health checks.

### Port conflicts
If ports 8000, 5432, or 6379 are taken, modify the `.env` file generated by `make setup`.

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)** - see the [LICENSE](LICENSE) file for details.

---

**Status**: 🚀 Active Development | **Version**: 0.2.0-alpha
