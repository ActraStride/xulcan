# -----------------------------------------------------------------------------
# ETAPA 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instalar herramientas de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear entorno virtual
RUN python -m venv /app/.venv

# MEJORA: Actualizar pip dentro del entorno virtual antes de instalar nada
RUN /app/.venv/bin/pip install --upgrade pip

# Instalar dependencias
COPY requirements.txt .
RUN /app/.venv/bin/pip install -r requirements.txt

# -----------------------------------------------------------------------------
# ETAPA 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Instalar dependencias runtime y limpiar caché en la misma capa (Mejor práctica)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario
RUN useradd -m -u 1000 xulcan && \
    chown -R xulcan:xulcan /app

# Copiar venv desde builder
COPY --from=builder --chown=xulcan:xulcan /app/.venv /app/.venv

# Copiar código fuente
COPY --chown=xulcan:xulcan . .

# Cambiar usuario
USER xulcan

# Exponer puerto y Healthcheck
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando final
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]