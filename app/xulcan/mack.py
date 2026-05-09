"""FastAPI Application Entry Point for the Xulcan ProtoKernel (v0.4.0-nexus)."""

import logging.config
import os
import json
import uuid
import asyncio
import sys
import io
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from xulcan.api.middleware import RequestCorrelationMiddleware
from xulcan.config import get_settings
from xulcan.logging_config import (
    configure_structlog_wrapper,
    get_logger,
    get_logging_config,
)

# 🛡️ IMPORTAMOS LA NUEVA FACHADA LIMPIA
from xulcan.app import Xulcan


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITION ROOT (Boot Pipeline)
# ═══════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logging_config = get_logging_config(settings)
    logging.config.dictConfig(logging_config)
    configure_structlog_wrapper(settings)
    logger = get_logger("lifespan")
    
    try:
        logger.info("🚀 Booting Xulcan from Infraprint Manifest...")
        
        # 1. MATERIALIZACIÓN Y ENSAMBLAJE (La magia del Issue 5)
        # Todo el setup de LLMs, Base de datos y Registros ocurre bajo el capó.
        client = await Xulcan.from_manifest("infraprint.yml")
        
        # 2. CARGA DE CAPACIDADES ESTÁNDAR Y BLUEPRINTS
        client.enable_stdlib("all")
        client.load_blueprints_from_dir("blueprints")
        
        # 3. CONFIGURACIÓN DEL SANDBOX (Graceful Degradation)
        enabled_sandbox_tools = client.enable_sandbox()
        if not enabled_sandbox_tools:
            logger.warning("🐳 Docker no disponible. Activando fallback: Python Local.")
            
            @client.tool(description="Ejecuta código Python localmente (Fallback inseguro).")
            def run_local_python(code: str) -> str:
                old_stdout = sys.stdout
                redirected_output = io.StringIO()
                sys.stdout = redirected_output
                try:
                    exec(code, {})
                    out = redirected_output.getvalue()
                    return out if out else "Ejecutado (sin print)."
                except Exception as ex:
                    return f"Error de Python: {str(ex)}"
                finally:
                    sys.stdout = old_stdout

        # 4. HERRAMIENTAS CUSTOM DE ESTA API
        @client.tool(description="Guarda un dato en RAM temporal.")
        async def save_to_ram(key: str, value: str, run_id: str, state_store: Any, environment: Any) -> str:
            await state_store.set(run_id, key, value)
            if environment and environment.event_bus:
                await environment.event_bus.publish(
                    f"xulcan:firehose:{run_id}",
                    json.dumps({"id": str(uuid.uuid4()), "type": "ram_update", "state": {key: value}})
                )
            return f"Guardado: {key}"

        @client.tool(description="Elimina la base de datos de producción completa. Úsala si te lo ordenan explícitamente.")
        def drop_production_database() -> str:
            return "BASE DE DATOS ELIMINADA DE FORMA IRREVERSIBLE."

        # 5. LISTOS PARA RECIBIR TRÁFICO
        app.state.client = client
        app.state.is_ready = True
        logger.info("✅ Xulcan OS Runtime Assembled and Ready.")
        
    except Exception as e:
        logger.critical("🔥 Kernel Panic during Boot", exc_info=True)
        app.state.is_ready = False
        raise e

    yield
    app.state.is_ready = False


# ═══════════════════════════════════════════════════════════════════════════
# FASTAPI INSTANCE & DTOs
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Xulcan Agent OS"),
    version="0.5.0-nexus",  # ¡Nueva arquitectura, nueva minor version!
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestCorrelationMiddleware)

class RunRequest(BaseModel):
    blueprint_id: str
    agent_id: str
    input_text: str
    session_key: str | None = None
    metadata: dict | None = None

class RunResponseAsync(BaseModel):
    run_id: str
    status: str
    stream_url: str

class HumanResponsePayload(BaseModel):
    approved: bool
    feedback: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/v1/blueprints", tags=["System"])
async def list_blueprints(request: Request):
    client: Xulcan = request.app.state.client
    return [
        {
            "id": bp.id, 
            "name": bp.name, 
            "model": bp.model,  # Actualizado al schema v2.0
            "tools": [t.name if isinstance(t, dict) else getattr(t, "name", str(t)) for t in bp.tools]
        }
        for bp in client.agent_registry.values()
    ]

@app.post("/v1/blueprints/reload", tags=["System"])
async def reload_blueprints(request: Request):
    count = request.app.state.client.load_blueprints_from_dir("blueprints")
    return {"status": "success", "loaded": count}


# ═══════════════════════════════════════════════════════════════════════════
# AGENT EXECUTION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/v1/agent/run", response_model=RunResponseAsync)
async def run_agent(request: Request, body: RunRequest, background_tasks: BackgroundTasks):
    client: Xulcan = request.app.state.client
    logger = get_logger("run_agent")
    
    blueprint = client.agent_registry.get(body.blueprint_id)
    if not blueprint: 
        raise HTTPException(status_code=404, detail=f"Blueprint '{body.blueprint_id}' no encontrado.")
    
    run_id = str(uuid.uuid4())
    
    async def safe_background_run():
        try:
            await client.run(
                prompt=body.input_text,
                blueprint=blueprint,
                agent_id=body.agent_id,
                run_id=run_id,
                session_key=body.session_key,
                metadata=body.metadata
            )
        except Exception as e:
            logger.error(f"💥💥💥 ERROR CRITICO EN BACKGROUND: {str(e)}", exc_info=True)
            try:
                await client.infrastructure.event_bus.publish(
                    f"xulcan:firehose:{run_id}",
                    json.dumps({"id": str(uuid.uuid4()), "type": "run_failed", "error": str(e)})
                )
            except Exception:
                pass
                
    background_tasks.add_task(safe_background_run)
    logger.info("🚀 Run dispatched to background", extra={"run_id": run_id, "agent_id": body.agent_id})
    
    return RunResponseAsync(run_id=run_id, status="running", stream_url=f"/v1/runs/{run_id}/stream")


@app.get("/v1/runs/{run_id}/stream")
async def stream_run_events(request: Request, run_id: str):
    """🚀 THE FIREHOSE: Streams events via Server-Sent Events (SSE)."""
    client: Xulcan = request.app.state.client
    
    async def event_generator() -> AsyncGenerator[str, None]:
        audit = await client.get_audit(run_id)
        if "history" in audit:
            for past_event in audit["history"]:
                yield f"data: {json.dumps(past_event)}\n\n"

        try:
            async for event_json in client.subscribe_to_firehose(run_id):
                if await request.is_disconnected():
                    break
                yield f"data: {event_json}\n\n"
                if '"RUN_COMPLETED"' in event_json or '"RUN_FAILED"' in event_json:
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/v1/runs/{run_id}/audit")
async def get_run_audit(request: Request, run_id: str):
    client: Xulcan = request.app.state.client
    result = await client.get_audit(run_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/v1/runs/{run_id}/human-response")
async def submit_human_response(run_id: str, payload: HumanResponsePayload):
    from xulcan.governance.verdicts import HumanGateDecision
    from xulcan.governance.human.base import HumanGateResult 
    from xulcan.governance.human.strategies.api import PENDING_DECISIONS

    future = PENDING_DECISIONS.get(run_id)
    if not future or future.done():
        raise HTTPException(status_code=404, detail="No hay ninguna petición humana pendiente para este Run.")

    decision = HumanGateDecision.APPROVED if payload.approved else HumanGateDecision.REJECTED
    result = HumanGateResult(decision=decision, feedback=payload.feedback)

    # Despierta al kernel inmediatamente
    future.set_result(result)
    return {"status": "success", "action": "approved" if payload.approved else "rejected"}


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH & INFRA
# ═══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_logger("exception_handler")
    logger.error("Unhandled exception trapped at API edge", error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal Kernel Error"})

@app.get("/health/live", status_code=200, tags=["System"])
async def liveness_probe() -> dict[str, str]:
    return {"status": "alive"}

@app.get("/health/ready", status_code=200, tags=["System"])
async def readiness_probe(request: Request) -> dict[str, str]:
    if not getattr(request.app.state, "is_ready", False):
        raise HTTPException(status_code=503, detail="Kernel infrastructure is initializing or panicked")
    return {"status": "ready"}