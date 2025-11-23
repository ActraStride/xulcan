#!/bin/bash
# Boots the Xulcan development environment

set -e

echo "🚀 Starting Xulcan (Core) in development mode..."

# Ensure a .env exists; scaffold it from .env.example when missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️  Missing .env file, creating it from .env.example..."
        cp .env.example .env
        echo "✅ .env created. Review the variables before continuing."
    else
        echo "❌ Neither .env nor .env.example found. Please add one before continuing."
        exit 1
    fi
fi

# Build images (important after dependency changes)
echo "🏗️  Checking/Building Docker images..."
docker-compose build

# Start the entire stack and wait for dependencies to report healthy
# depends_on/service_healthy takes care of waiting for Postgres and Redis
echo "▶️  Bringing services online..."
docker-compose up -d

echo "✅ Xulcan is up and running!"
echo ""
echo "📍 Available endpoints:"
echo "   - API:  http://localhost:8000"
echo "   - Docs: http://localhost:8000/docs"
echo "   - Logs: docker-compose logs -f app"
echo ""
echo "Stop services with: docker-compose down"