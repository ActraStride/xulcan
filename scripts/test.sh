#!/bin/bash
# Runs the test suite inside the containerized environment.
# This script ensures the necessary services are running and executes pytest
# with the configuration defined in pytest.ini.

set -euo pipefail # Fail fast on errors, undefined variables, and pipe failures

echo "🧪 Preparing the test environment..."

# Use Docker Compose to get the status of the app service.
# This is more robust than parsing `ps` output.
APP_SERVICE_STATUS=$(docker compose ps -q --status=running app)

# Start services only if the app container is not already running.
if [ -z "$APP_SERVICE_STATUS" ]; then
    echo "⚠️  App service is not running. Starting required services..."
    # `-d` starts in detached mode.
    # We only need `app` and its dependencies (`postgres`, `redis`).
    # The dev tools (`pgadmin`, etc.) are not needed for testing.
    docker compose up -d app
    echo "✅ Services started."
fi

echo "▶️  Running pytest suite..."

# Execute pytest inside the 'app' service container.
# -e PYTHONPATH=/app: Ensures Python can find the 'xulcan' package.
# All other pytest arguments are now sourced from `pytest.ini`.
docker compose exec -e PYTHONPATH=/app app pytest xulcan/ tests/

echo ""
echo "✅ Test run finished."
echo "📊 Coverage report generated in 'htmlcov/'."