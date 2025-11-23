#!/bin/bash
# Script para ejecutar tests dentro del contenedor

set -e

echo "🧪 Preparando entorno de pruebas..."

# Verificar si el servicio app está corriendo
if ! docker-compose ps | grep -q "xulcan-core"; then
    echo "⚠️  El contenedor de la app no está corriendo."
    echo "    Iniciando infraestructura mínima para tests..."
    docker-compose up -d
fi

echo "▶️  Ejecutando pytest..."
# Usamos 'exec' para correr los tests dentro del contenedor que ya tiene el entorno configurado
docker-compose exec app pytest tests/ -v --cov=app --cov-report=html --cov-report=term

echo ""
echo "✅ Tests finalizados."
echo "📊 Si ejecutaste con coverage, revisa la carpeta 'htmlcov' en tu directorio local."