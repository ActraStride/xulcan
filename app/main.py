"""Xulcan API application entry point.

Initialize and configure the FastAPI application instance for the
Xulcan AI Agent orchestration framework.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Xulcan API",
    description="API-first framework for AI Agent orchestration",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Return application health status.

    Returns:
        Dictionary containing the current health status.
    """
    return {"status": "ok"}
