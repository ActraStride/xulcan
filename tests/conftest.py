"""Test configuration and shared fixtures.

Provide isolated test settings and client fixtures for the application test suite.
All fixtures ensure tests run without external dependencies on environment files or secrets.
"""
import os
from typing import Generator
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings, get_settings

# ==============================================================================
# CONFIGURATION FIXTURES
# ==============================================================================

@pytest.fixture(scope="session")
def mock_settings() -> Settings:
    """Provide isolated test configuration without external dependencies.

    Returns:
        Settings: Test configuration with development environment, test credentials,
            and file-based secret loading disabled.
    """
    return Settings(
        ENVIRONMENT="development",
        LOG_LEVEL="debug",
        SECRET_KEY="test_secret_key_for_unit_tests",
        # Disable file-based secret loading to prevent I/O errors during tests
        POSTGRES_PASSWORD_FILE=None,
        REDIS_PASSWORD_FILE=None,
        # Provide test credentials to satisfy Pydantic validators
        POSTGRES_PASSWORD="test_pg_pass",
        REDIS_PASSWORD="test_redis_pass",
        _env_file=None  # Bypass production environment file
    )

@pytest.fixture(scope="function")
def client(mock_settings: Settings) -> Generator[TestClient, None, None]:
    """Provide HTTP test client with isolated dependency injection.

    Preserve original dependency overrides and restore them after test completion
    to prevent test isolation issues.

    Args:
        mock_settings: Isolated test configuration.

    Yields:
        TestClient: FastAPI test client with mocked settings.
    """
    # Preserve original dependency state
    original_override = app.dependency_overrides.get(get_settings)
    
    # Apply test configuration override
    app.dependency_overrides[get_settings] = lambda: mock_settings
    
    # Ensure application readiness state
    app.state.is_ready = True
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Restore original dependency state
    if original_override:
        app.dependency_overrides[get_settings] = original_override
    else:
        app.dependency_overrides.pop(get_settings, None)

# ==============================================================================
# MOCKING HELPERS
# ==============================================================================

@pytest.fixture
def mock_fs_open():
    """Provide mock for file system operations.

    Yields:
        Mock: Patched builtins.open to intercept file I/O during configuration tests.
    """
    with mock.patch("builtins.open", mock.mock_open()) as mock_file:
        yield mock_file