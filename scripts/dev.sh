#!/bin/bash
# Script para iniciar el entorno de desarrollo de Xulcan

set -e

echo "🚀 Iniciando Xulcan (Core) en modo desarrollo..."

# Verificar si existe .env, si no, crear desde .env.example
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️  No se encontró archivo .env, creando desde .env.example..."
        cp .env.example .env
        echo "✅ Archivo .env creado. REVISA TUS VARIABLES antes de continuar."
    else
        echo "❌ No se encontró .env ni .env.example. Por favor crea uno."
        exit 1
    fi
fi

# Construir imágenes (importante tras cambios en requirements)
echo "🏗️  Verificando/Construyendo imágenes Docker..."
docker-compose build

# Iniciar todo el stack
# Nota: Gracias a 'depends_on: service_healthy' en el docker-compose, 
# la app esperará automáticamente a que Postgres y Redis estén verdes.
echo "▶️  Levantando servicios..."
docker-compose up -d

echo "✅ Xulcan está corriendo!"
echo ""
echo "📍 Endpoints disponibles:"
echo "   - API:  http://localhost:8000"
echo "   - Docs: http://localhost:8000/docs"
echo "   - Logs: docker-compose logs -f app"
echo ""
echo "Para detener: docker-compose down"