#!/bin/bash
# Script para limpiar contenedores, volúmenes y caché

set -e

echo "🧹 Limpiando entorno de Xulcan..."

# Detener contenedores y eliminar redes huérfanas
echo "⏹️  Deteniendo servicios..."
docker-compose down --remove-orphans

# Preguntar por limpieza profunda (Volúmenes)
read -p "WARNING: ¿Eliminar base de datos y caché de Redis (Volúmenes)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Eliminando volúmenes persistentes..."
    docker-compose down -v
    echo "✅ Datos eliminados."
fi

# Limpieza de archivos locales de Python (pycache, pytest_cache)
# Esto es útil porque el volumen montado a veces deja basura en tu host
echo "🧹 Limpiando archivos temporales locales (__pycache__, .pytest_cache)..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type d -name ".mypy_cache" -exec rm -rf {} +
find . -type d -name "htmlcov" -exec rm -rf {} +

echo "✅ Limpieza completa. Tu entorno está como nuevo."