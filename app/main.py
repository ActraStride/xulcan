"""FastAPI application entry point for the Xulcan orchestration framework.

Define the FastAPI application instance, register middleware, and configure
the application lifespan for startup and shutdown event management. Confine
all side effects (logging, database connections) to the lifespan context
manager to ensure a predictable initialization order.
"""

import logging.config
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.middleware import RequestCorrelationMiddleware
from app.config import Settings, get_settings
from app.core.logging_config import (
    configure_structlog_wrapper,
    get_logger,
    get_logging_config,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle events.

    Initialize resources on startup and release them on shutdown. Confine all
    side effects (logging configuration, database connections, cache pools)
    to this context manager.

    Args:
        app: FastAPI application instance.

    Yields:
        None: Control returns to the application after startup completes.

    Raises:
        Exception: Propagate critical errors when resource initialization fails.
    """
    # === STARTUP SEQUENCE ===

    settings = get_settings()

    # Configure standard library logging (handlers, formatters)
    logging_config = get_logging_config(settings)
    logging.config.dictConfig(logging_config)

    # Configure structlog processors for application code
    configure_structlog_wrapper(settings)

    logger = get_logger("lifespan")
    logger.info("🚀 Xulcan System Startup Initiated", extra={"env": settings.ENVIRONMENT})

    # Initialize shared resources and attach to app.state for dependency injection
    try:
        app.state.is_ready = True
        logger.info("Resources initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize resources: {e}")
        app.state.is_ready = False
        raise e

    yield

    # === SHUTDOWN SEQUENCE ===

    logger.info("🛑 Xulcan System Shutdown Initiated")
    app.state.is_ready = False
    logger.info("Resources released")


app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Xulcan"),
    version=os.getenv("VERSION", "0.1.0"),
    description="API-first framework for AI Agent orchestration",
    lifespan=lifespan,
)

app.add_middleware(RequestCorrelationMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions globally.
    
    Catches any exception not handled by specific route handlers. Logs the
    full error with structured context (including request_id) and returns
    a generic 500 JSON response to the client to avoid leaking internal details.
    """
    # Import logger locally or use a module-level one if available
    logger = get_logger("exception_handler")
    
    # Log with full traceback and context
    logger.error(
        "Unhandled exception occurred",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True # This ensures the stack trace is included in the log
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal Server Error", 
            # Optionally include request_id in the error response for support
            "request_id": request.headers.get("X-Request-ID") 
        },
    )


@app.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Return liveness status for container orchestration.

    Provide a lightweight endpoint for orchestrators (e.g., Kubernetes) to
    determine whether the container requires a restart. This probe does not
    verify external dependencies such as databases or caches.

    Returns:
        dict[str, str]: Status indicator confirming the process is alive.
    """
    return {"status": "alive"}


@app.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(request: Request) -> dict[str, str]:
    """Return readiness status for traffic routing decisions.

    Verify that the application has completed initialization and all critical
    dependencies are available. Use this probe to control traffic routing in
    load balancers and container orchestrators.

    Args:
        request: Incoming HTTP request object.

    Returns:
        dict[str, str]: Status indicator confirming readiness.

    Raises:
        HTTPException: 503 Service Unavailable when dependencies are not ready.
    """
    if not getattr(request.app.state, "is_ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is starting up or dependencies are unavailable"
        )

    return {"status": "ready"}


@app.get("/health", include_in_schema=False)
async def legacy_health() -> dict[str, str]:
    """Return health status for backward compatibility.

    .. deprecated::
        Use ``/health/live`` or ``/health/ready`` instead.

    Returns:
        dict[str, str]: Status with deprecation notice.
    """
    return {"status": "ok", "note": "deprecated: use /health/live or /health/ready"}