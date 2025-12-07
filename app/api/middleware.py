"""HTTP middleware for request correlation and structured logging.

Provide middleware to manage request-scoped context variables, specifically
the Request ID, enabling distributed tracing across the application.
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import bind_contextvars, clear_contextvars, get_logger

logger = get_logger(__name__)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Manage request correlation IDs for distributed tracing.

    Ensure every request has a unique ID bound to the logging context via
    `structlog.contextvars`. This ID is automatically included in all log
    entries generated during the request lifecycle.
    """

    async def dispatch(self, request: Request, call_next):
        """Process the request and manage correlation context lifecycle.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler in the chain.

        Returns:
            The HTTP response with the `X-Request-ID` header attached.
        """
        # Clear residual context from previous requests to prevent leakage
        # in async environments where context may persist across tasks.
        clear_contextvars()

        # Extract existing Request ID from upstream (load balancer, API gateway)
        # or generate a new UUID if none is provided.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind request_id to the logging context, making it available to all
        # loggers within this request scope.
        bind_contextvars(request_id=request_id)

        # Delegate to the next handler. Unhandled exceptions propagate to
        # global exception handlers, which retain access to the bound context.
        response: Response = await call_next(request)

        # Propagate correlation ID to downstream consumers via response header.
        response.headers["X-Request-ID"] = request_id

        return response