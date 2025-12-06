# ==================================================================================
# XULCAN API - PRODUCTION DOCKERFILE
# ==================================================================================
# Description: Multi-stage build for minimal image size and maximum security.
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

# [OPS] Install system build dependencies required for compiling Python packages.
#       - build-essential: Provides gcc and make for native extensions.
#       - libpq-dev: Headers for building psycopg2.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# [ARC] Create isolated virtual environment.
RUN python -m venv /app/.venv
RUN /app/.venv/bin/pip install --upgrade pip

# ----------------------------------------------------------------------------------
# DEPENDENCY LAYER CACHING STRATEGY
# ----------------------------------------------------------------------------------
# Copy and install production dependencies first to maximize Docker layer caching.
# Subsequent builds skip this step if requirements.txt remains unchanged.
COPY requirements.txt .
RUN /app/.venv/bin/pip install -r requirements.txt

# [OPS] Conditionally install development dependencies based on build argument.
ARG INSTALL_DEV=false
COPY requirements-dev.txt .
RUN if [ "$INSTALL_DEV" = "true" ]; then /app/.venv/bin/pip install -r requirements-dev.txt; fi

# ----------------------------------------------------------------------------------
# STAGE 2: RUNTIME
# ----------------------------------------------------------------------------------
# Create a secure, lightweight execution environment containing only the necessary
# binaries and the pre-built virtual environment.
FROM python:3.11.14-slim-bookworm AS runtime

# [OPS] Add virtual environment to PATH for native command execution.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# [SEC] Install only runtime libraries to minimize attack surface.
#       - libpq5: Shared library required by psycopg2 at runtime.
# [OPS] Clean apt cache immediately to keep the layer small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# [SEC] Implement Least Privilege Principle with non-root user.
RUN useradd -m -u 1000 xulcan && \
    chown -R xulcan:xulcan /app

# [ARC] Copy virtual environment from builder stage.
COPY --from=builder --chown=xulcan:xulcan /app/.venv /app/.venv

# [APP] Copy application source code.
COPY --chown=xulcan:xulcan . .

# [SEC] Switch execution context to non-root user.
USER xulcan

# [NET] Document exposed port for container orchestration.
EXPOSE 8000

# [OPS] Configure container healthcheck using native Python script.
#       Avoids curl dependency to reduce image size.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python app/healthcheck.py || exit 1

# [RUN] Start the ASGI server.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]