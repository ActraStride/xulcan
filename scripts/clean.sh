#!/bin/bash
# Cleans containers, volumes, and cached artifacts in the local environment

set -e

echo "🧹 Cleaning the Xulcan environment..."

# Stop containers and remove orphaned networks
echo "⏹️  Stopping services..."
docker-compose down --remove-orphans

# Preguntar por limpieza profunda (Volúmenes)
read -p "WARNING: Remove database and Redis cache volumes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Removing persistent volumes..."
    docker-compose down -v
    echo "✅ Data removed."
fi

# Remove local Python artifacts (pycache, pytest cache, mypy cache, coverage)
# Useful because the bind mount can leave leftover artifacts on your host
echo "🧹 Removing local temporary files (__pycache__, .pytest_cache)..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type d -name ".mypy_cache" -exec rm -rf {} +
find . -type d -name "htmlcov" -exec rm -rf {} +

echo "✅ Cleanup complete. You're ready to go."