"""Test suite for structured logging configuration.

This module validates that the logging system correctly configures formatters,
processors, and context variables for both production and development environments.
"""
import pytest
import structlog
from xulcan.config import Settings
from xulcan.core.logging_config import get_logging_config, get_common_processors, bind_contextvars, clear_contextvars

def test_config_generates_json_in_production():
    """Verify production environment uses JSON renderer for structured logging.
    
    Production mode requires machine-readable JSON output for centralized
    log aggregation and analysis.
    """
    # Production environment requires a valid SECRET_KEY for Settings validation
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a_valid_production_secret_key_for_testing",
        _env_file=None
    )
    
    config = get_logging_config(settings)
    
    # Verify the default formatter uses JSON renderer
    processor = config["formatters"]["default"]["processor"]
    assert isinstance(processor, structlog.processors.JSONRenderer)

def test_config_generates_console_in_development():
    """Verify development environment uses console renderer with color output.
    
    Development mode provides human-readable colored console output for
    improved developer experience during local debugging.
    """
    settings = Settings(ENVIRONMENT="development", _env_file=None)
    config = get_logging_config(settings)
    
    processor = config["formatters"]["default"]["processor"]
    assert isinstance(processor, structlog.dev.ConsoleRenderer)

def test_common_processors_include_context_merge():
    """Verify merge_contextvars processor is present in the processing chain.
    
    The merge_contextvars processor is critical for correlation ID propagation.
    Without it, request tracing middleware cannot inject contextual metadata
    into log entries.
    """
    processors = get_common_processors()
    assert structlog.contextvars.merge_contextvars in processors

def test_contextvars_binding_and_clearing():
    """Verify context variable binding and clearing utilities function correctly."""
    # Bind a request ID to the current context
    bind_contextvars(request_id="test-123")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "test-123"
    
    # Clear all context variables
    clear_contextvars()
    ctx = structlog.contextvars.get_contextvars()
    assert "request_id" not in ctx