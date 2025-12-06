# ==================================================================================
# XULCAN API - PRODUCTION DOCKERFILE
# ==================================================================================
# Description: Multi-stage build strategy to ensure minimal image size and
#              maximum security by separating build artifacts from runtime.
# Standard:    OCI Compliant
# Security:    Non-root execution, ephemeral build dependencies.
# ==================================================================================

# ----------------------------------------------------------------------------------
# STAGE 1: BUILDER
# ----------------------------------------------------------------------------------
FROM python:3.11.14-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OPS: Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ARC: Create virtual environment
RUN python -m venv /app/.venv
RUN /app/.venv/bin/pip install --upgrade pip

# --- OPTIMIZACIÓN DE CACHÉ ---
# 1. Copiamos SOLO los requerimientos de producción primero.
COPY requirements.txt .
# 2. Instalamos. Esto crea una capa cacheada. Si requirements.txt no cambia, Docker salta este paso.
RUN /app/.venv/bin/pip install -r requirements.txt

# 3. Argumento de construcción
ARG INSTALL_DEV=false

# 4. Copiamos y condicionalmente instalamos dev deps.
#    Si modificas requirements-dev.txt, solo se invalida de aquí para abajo.
COPY requirements-dev.txt .
RUN if [ "$INSTALL_DEV" = "true" ]; then /app/.venv/bin/pip install -r requirements-dev.txt; fi

# ----------------------------------------------------------------------------------
# STAGE 2: RUNTIME
# Goal: Create a secure, lightweight execution environment.
#       Contains ONLY the necessary binaries and the pre-built venv.
# ----------------------------------------------------------------------------------
FROM python:3.11.14-slim-bookworm AS runtime

# OPS: Add venv to PATH to ensure `python` and `uvicorn` commands work natively
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# SEC: Install ONLY runtime libraries.
#      - libpq5: Shared object required by psycopg2 at runtime.
# OPS: Clean apt cache immediately to keep the layer small.
# NOTA: Hemos quitado 'curl' porque usamos healthcheck nativo de Python.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# SEC: Implement Least Privilege Principle.
RUN useradd -m -u 1000 xulcan && \
    chown -R xulcan:xulcan /app

# ARC: Copy venv from builder
COPY --from=builder --chown=xulcan:xulcan /app/.venv /app/.venv

# APP: Copy application source code.
# Esto copiará 'app/healthcheck.py' si está en tu carpeta local 'app/'.
COPY --chown=xulcan:xulcan . .

# SEC: Switch context to non-root user.
USER xulcan

# NET: Document port
EXPOSE 8000

# OPS: Orchestrator Healthcheck (Native Python)
#      Replaced 'curl' with a lightweight Python script to reduce image size and deps.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python app/healthcheck.py || exit 1

# RUN: Start the ASGI server.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]