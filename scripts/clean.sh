#!/bin/bash
# Cleans containers, volumes, and cached artifacts in the local environment

# 'set -e' hace que el script se detenga inmediatamente si ocurre un error inesperado.
set -e

echo "🧹 Cleaning the Xulcan environment..."

# 1. Detener contenedores
# --remove-orphans: Limpia contenedores viejos que ya no están en el docker-compose.yml
echo "⏹️  Stopping services..."
docker compose down --remove-orphans

# 2. Limpieza de Volúmenes (Opcional e Interactiva)
# Pregunta al usuario antes de borrar la base de datos para evitar accidentes.
read -p "WARNING: Remove database and Redis cache volumes? (y/N): " -n 1 -r
echo # Salto de línea estético
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Removing persistent volumes..."
    # 'down -v' es el comando que destruye los volúmenes nombrados (postgres_data, etc.)
    docker compose down -v
    echo "✅ Data removed."
fi

# 3. Limpieza de basura de Python
# Eliminamos carpetas de caché para evitar conflictos entre ejecuciones locales y de Docker.
echo "🧹 Removing local temporary files (__pycache__, .pytest_cache)..."

# NOTA TÉCNICA:
# Usamos '2>/dev/null || true' al final.
# Esto sirve para que, si Docker creó algún archivo como 'root' y tu usuario
# no puede borrarlo, el script NO se rompa, simplemente lo ignore y siga.
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || echo "⚠️  Some system files were locked (root owned). Skipping."
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

echo "✅ Cleanup complete. You're ready to go."