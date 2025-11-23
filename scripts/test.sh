#!/bin/bash
# Runs the test suite inside the containerized environment

set -e

echo "🧪 Preparing the test environment..."

# Ensure the app service is running before executing tests
if ! docker compose ps | grep -q "xulcan-core"; then
    echo "⚠️  The app container is not running."
    echo "    Starting the minimum infrastructure required for tests..."
    docker compose up -d
fi

echo "▶️  Running pytest..."
# Use exec so tests run inside the container with the configured environment
docker compose exec app pytest tests/ -v --cov=app --cov-report=html --cov-report=term

echo ""
echo "✅ Test run finished."
echo "📊 If you enabled coverage, inspect the 'htmlcov' folder in your local directory."