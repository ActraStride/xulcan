"""Configuration settings test suite.

Validate secure credential handling, secret masking, and database URL
construction for the application configuration module.
"""
import os
from unittest import mock
import pytest
from app.config import Settings


def test_password_file_takes_precedence_over_env_var(mock_fs_open):
    """Verify password file precedence over environment variables.
    
    Ensure that when both a password file and environment variable are present,
    the Docker secrets file takes precedence for secure credential handling.
    """
    mock_fs_open.return_value.read.return_value = "secret_from_file"

    env_vars = {
        "POSTGRES_PASSWORD_FILE": "/run/secrets/pg_pass",
        "POSTGRES_PASSWORD": "secret_from_env_var_BAD", 
    }

    with mock.patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(_env_file=None)
        
        db_url = str(settings.DATABASE_URL)
        
        assert "secret_from_file" in db_url
        assert "secret_from_env_var_BAD" not in db_url
        
        # Validate file open was called with correct path.
        # Pydantic may call open() multiple times during lazy validation.
        mock_fs_open.assert_called_with("/run/secrets/pg_pass", "r")

def test_password_env_var_used_when_file_is_none():
    """Verify fallback to environment variable when no password file exists.
    
    Ensures the application uses POSTGRES_PASSWORD when no password file
    is specified.
    """
    env_vars = {
        "POSTGRES_PASSWORD_FILE": "",
        "POSTGRES_PASSWORD": "secret_from_env_var_OK",
    }
    with mock.patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(_env_file=None)
        assert "secret_from_env_var_OK" in str(settings.DATABASE_URL)

def test_secret_key_is_masked():
    """Verify that sensitive values are masked in configuration dumps.
    
    Ensures SecretStr fields do not expose sensitive data when the
    configuration is serialized or printed.
    """
    settings = Settings(SECRET_KEY="super_sensitive_data", _env_file=None)
    dumped = str(settings.model_dump())
    
    assert "super_sensitive_data" not in dumped
    assert settings.SECRET_KEY.get_secret_value() == "super_sensitive_data"

def test_computed_dsn_asyncpg_driver():
    """Verify that database URL uses the asynchronous PostgreSQL driver.
    
    Ensures the constructed DATABASE_URL uses the postgresql+asyncpg
    driver for async operations.
    """
    settings = Settings(POSTGRES_PASSWORD="pass", _env_file=None)
    assert str(settings.DATABASE_URL).startswith("postgresql+asyncpg://")