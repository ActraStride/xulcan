"""FastAPI Application Entry Point for the Xulcan ProtoKernel.

This module serves as the "Composition Root" of the application. It is the only
place in the system where the Domain Layer (Kernel, Models) is allowed to mix 
with the Infrastructure Layer (FastAPI, Ledgers, Adapters).
"""

import logging.config
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════════════
# XULCAN IMPORTS
# ═══════════════════════════════════════════════════════════════════════════

from xulcan.api.middleware import RequestCorrelationMiddleware
from xulcan.config import get_settings
from xulcan.logging_config import (
    configure_structlog_wrapper,
    get_logger,
    get_logging_config,
)

from xulcan.kernel.orchestrator import ProtoKernel
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.protocol.message import UnifiedMessage
from xulcan.protocol.io import UnifiedResponse, FinishReason
from xulcan.protocol.tools import ToolCall
from xulcan.core.economics import UsageStats

from xulcan.memory.memory import InMemoryLedger
from xulcan.llm.adapters.mock import ScriptedMockAdapter
from xulcan.llm.adapters.gemini import GeminiAdapter   # <--- [NUEVO] Importamos tu adaptador
from xulcan.llm.registry import LLMRegistry
from xulcan.toools.local import LocalToolRegistry, LocalPythonExecutor


# ═══════════════════════════════════════════════════════════════════════════
# MOCK DOMAIN
# ═══════════════════════════════════════════════════════════════════════════

def calculator(a: int, b: int, op: str = "+") -> dict:
    """A simple deterministic tool for testing the Action phase of the FSM."""
    if op == "+": return {"result": a + b}
    if op == "-": return {"result": a - b}
    if op == "*": return {"result": a * b}
    return {"error": "unknown operator"}


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITION ROOT
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Obtenemos el Singleton de configuración (ya resolvió los Docker Secrets)
    settings = get_settings()
    
    logging_config = get_logging_config(settings)
    logging.config.dictConfig(logging_config)
    configure_structlog_wrapper(settings)
    logger = get_logger("lifespan")
    
    logger.info("🚀 Booting Xulcan ProtoKernel...", extra={"env": settings.ENVIRONMENT})

    try:
        ledger = InMemoryLedger()
        
        LocalToolRegistry.register("calculator", calculator)
        tool_executor = LocalPythonExecutor()

        # ---------------------------------------------------------
        # LLM REGISTRATION (The "Brain" Directory)
        # ---------------------------------------------------------
        
        # 1. Registramos el Mock (Ideal para Test Unitarios deterministas)
        response_1 = UnifiedResponse(
            content=None,
            tool_calls=[ToolCall(id="call_123", name="calculator", arguments={"a": 5, "b": 5, "op": "+"})],
            finish_reason=FinishReason.TOOL_CALLS,
            usage=UsageStats(input_tokens=5, output_tokens=5, total_tokens=10, latency_ms=100)
        )
        response_2 = UnifiedResponse(
            content="The result of 5 + 5 is 10. (Calculated with offset).",
            finish_reason=FinishReason.STOP,
            usage=UsageStats(input_tokens=10, output_tokens=10, total_tokens=20, latency_ms=100)
        )
        mock_llm = ScriptedMockAdapter(script=[response_1, response_2], latency_ms=100)
        LLMRegistry.register("mock", mock_llm)
        
        # 2. Registramos GEMINI (Tu adaptador Real)
        # Verificamos la variable segura manejada por Pydantic Settings
        if not settings.GEMINI_API_KEY:
            logger.warning("⚠️ GEMINI_API_KEY not found in ENV or Secrets. The Google adapter will fail if called.")
        else:
            # Usamos .get_secret_value() para desencapsular el SecretStr de Pydantic
            raw_api_key = settings.GEMINI_API_KEY.get_secret_value()
            gemini_real = GeminiAdapter(api_key=raw_api_key)
            
            LLMRegistry.register("google", gemini_real)
            logger.info("✅ Gemini Adapter successfully registered from secure settings.")

        # ---------------------------------------------------------
        
        kernel = ProtoKernel(
            repository=ledger, 
            llm_registry=LLMRegistry,
            tool_executor=tool_executor
        )

        app.state.kernel = kernel
        app.state.ledger = ledger
        app.state.is_ready = True
        
    except Exception as e:
        logger.critical("🔥 Kernel Panic during startup", error=str(e), exc_info=True)
        app.state.is_ready = False
        raise e

    yield

    logger.info("🛑 Xulcan Shutdown: Flushing memory and closing connections.")
    app.state.is_ready = False


# ═══════════════════════════════════════════════════════════════════════════
# FASTAPI INSTANCE & MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Xulcan ProtoKernel"),
    version="0.1.0-proto",
    lifespan=lifespan,
)

app.add_middleware(RequestCorrelationMiddleware)


class RunRequest(BaseModel):
    input_text: str

class RunResponse(BaseModel):
    run_id: str
    output: UnifiedMessage


# ═══════════════════════════════════════════════════════════════════════════
# AGENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/agent/run", response_model=RunResponse)
async def run_agent(request: Request, body: RunRequest):
    
    kernel: ProtoKernel = request.app.state.kernel
    
    # ---------------------------------------------------------
    # AGENT IDENTITY (Ahora usando Gemini!) <--- [MODIFICADO]
    # ---------------------------------------------------------
    blueprint = AgentBlueprint(
        id="proto-agent-v1",
        name="Proto Agent",
        version="1.0.0",
        description="A real agent running on Gemini Flash.",
        model_provider="google",         # Busca en el Registry a quien registramos como 'google'
        model_name="gemini-2.5-flash",   # El string que le pasamos a la API de Google
        system_prompt="You are a strict, helpful AI that uses tools.",
        temperature=0.0
    )
    
    run_id, response = await kernel.execute_run(
        blueprint=blueprint,
        user_input=body.input_text
    )
    
    return RunResponse(
        run_id=run_id,
        output=response
    )

# ... (resto de endpoints de health y audit se mantienen intactos) ...

@app.get("/runs/{run_id}/audit")
async def get_run_audit(request: Request, run_id: str):
    """Forensic endpoint for extracting the Dynamic DAG.
    
    Retrieves the complete, chronological event trace from the Ledger. 
    Crucial for debugging ReAct loops, observing tool inputs/outputs, 
    and auditing token usage per step.
    """
    
    ledger: InMemoryLedger = request.app.state.ledger
    
    if run_id not in ledger._store:
        raise HTTPException(status_code=404, detail="Run ID not found in Ledger")
        
    snapshot = await ledger.get_snapshot(run_id)
    events = await ledger.get_events(run_id)
    
    return {
        "snapshot": snapshot,
        "history": events
    }


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM ENDPOINTS (Kubernetes & Error Handling)
# ═══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for uncaught application errors to prevent data leaks."""
    logger = get_logger("exception_handler")
    logger.error("Unhandled exception trapped at API edge", error=str(exc), path=request.url.path, exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal Kernel Error", 
            "request_id": request.headers.get("X-Request-ID")
        },
    )

@app.get("/health/live", status_code=status.HTTP_200_OK, tags=["System"])
async def liveness_probe() -> dict[str, str]:
    """Liveness probe to verify the web server is responding."""
    return {"status": "alive"}

@app.get("/health/ready", status_code=status.HTTP_200_OK, tags=["System"])
async def readiness_probe(request: Request) -> dict[str, str]:
    """Readiness probe to verify the Kernel and DI container are fully initialized."""
    if not getattr(request.app.state, "is_ready", False):
        raise HTTPException(status_code=503, detail="Kernel infrastructure is initializing or panicked")
    return {"status": "ready"}