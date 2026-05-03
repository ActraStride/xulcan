"""FastAPI Application Entry Point for the Xulcan ProtoKernel."""

import logging.config
import os
import json
import uuid
import asyncio
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

# 🛡️ IMPORTAMOS TU CLIENTE MAESTRO
from xulcan.app import Xulcan
# Importamos tu blueprint loader para cargar un agente por defecto
from xulcan.blueprint.schema import AgentBlueprint

# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITION ROOT (Ahora delegado al Client)
# ═══════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logging_config = get_logging_config(settings)
    logging.config.dictConfig(logging_config)
    configure_structlog_wrapper(settings)
    logger = get_logger("lifespan")
    
    try:
        # En mack.py
        gemini_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
        groq_key = settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else None # Añade esto
        samba_key = settings.SAMBANOVA_API_KEY.get_secret_value() if hasattr(settings, 'SAMBANOVA_API_KEY') and settings.SAMBANOVA_API_KEY else os.getenv("SAMBANOVA_API_KEY")
        github_key = settings.GITHUB_TOKEN.get_secret_value() if settings.GITHUB_TOKEN else os.getenv("GITHUB_TOKEN")

        client = Xulcan(
            gemini_api_key=gemini_key,
            groq_api_key=groq_key,  # Y esto
            sambanova_api_key=samba_key,
            github_token=github_key
        )
        # 🚨 REGISTRAMOS LA PUERTA HUMANA PARA LA WEB (Paso 11)
        from xulcan.governance.human.strategies.api import ApiHumanGateStrategy
        client.human_gate_registry.register("api", ApiHumanGateStrategy)
        
        # Ahora sí, cargamos blueprints que podrían usar la estrategia 'api'
        client.load_blueprints_from_dir("blueprints")
        app.state.client = client
        
        client.enable_stdlib("all")
        
        # 🚨 REGISTRAMOS LA PUERTA HUMANA PARA LA WEB
        from xulcan.governance.human.strategies.api import ApiHumanGateStrategy
        client.human_gate_registry.register("api", ApiHumanGateStrategy)

        # 🐳 Degradación Docker vs Local
        python_tool_name = "sandbox_run_python"
        fallback_active = False
        try:
            client.enable_sandbox()
        except RuntimeError:
            python_tool_name = "run_local_python"
            fallback_active = True
            import sys, io
            @client.tool(description="Ejecuta código Python localmente.")
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

        @client.tool(description="Guarda un dato en RAM.")
        async def save_to_ram(key: str, value: str, run_id: str, state_store: Any, environment: Any) -> str:
            await state_store.set(run_id, key, value)
            if environment and environment.event_bus:
                import uuid, json
                await environment.event_bus.publish(
                    f"xulcan:firehose:{run_id}",
                    json.dumps({"id": str(uuid.uuid4()), "type": "ram_update", "state": {key: value}})
                )
            return f"Guardado: {key}"

        # 💀 LA HERRAMIENTA PROHIBIDA
        @client.tool(description="Elimina la base de datos de producción completa. Úsala si te lo ordenan explícitamente.")
        def drop_production_database() -> str:
            return "BASE DE DATOS ELIMINADA DE FORMA IRREVERSIBLE."

        tools_list =[
            {"name": "network_fetch_webpage", "enabled": True},
            {"name": "save_to_ram", "enabled": True},
            {"name": "drop_production_database", "enabled": True},
            {"name": python_tool_name, "enabled": True}
        ]
        
        if not fallback_active:
            tools_list.extend([
                {"name": "sandbox_run_bash", "enabled": True},
                {"name": "sandbox_read_file", "enabled": True},
                {"name": "sandbox_write_file", "enabled": True}
            ])

        # 🧠 EL BLUEPRINT CON EL NUEVO ESQUEMA 2.0
        agent_dict = dict(
            xulcan_version="2.0",  # <--- INDISPENSABLE
            id="nexus-complex-tester",
            name="Nexus Security & Research",
            
            # 1. MODELO PRINCIPAL (Usando el nuevo ModelSpec)
            model="google/gemini-2.0-flash", # Slash syntax (Paso 1)
            # Nota: temperature se puede pasar aquí o dentro de un dict
            
            # 🚀 2. REFUERZOS (Estructura corregida)
            fallbacks=[
                {
                    "provider": "github", 
                    "name": "openai/gpt-4o-mini", # Corregido: campo 'name'
                    "temperature": 0.1
                }
            ],

            system_prompt=(
                "Eres un agente de operaciones altamente resiliente.\n"
                "Tu objetivo es ejecutar comandos Linux y gestionar la base de datos."
            ),
            context="full_history", # Shorthand (Paso 6)
            
            # Gobernanza Global (Solo Budget ahora)
            governance=dict(
                budget="unlimited"
            ),
            
            # 🛡️ GOBERNANZA POR TOOL (La gran novedad del refactor)
            tools=[
                {"name": "network_fetch_webpage"},
                {"name": "save_to_ram"},
                {
                    "name": "drop_production_database",
                    "governance": {
                        "sentinel": {
                            "strategy": "blocklist",
                            "params": {"blocked_tools": ["drop_production_database"]}
                        },
                        "human_gate": {
                            "strategy": "api",
                            "params": {"timeout_seconds": 300.0}
                        }
                    }
                },
                {"name": python_tool_name}
            ]
        )
        
        default_agent = client.load_agent(agent_dict)
        app.state.default_agent = default_agent
        app.state.client = client
        app.state.is_ready = True
        
        logger.info("✅ Complex Agent with Double Defense loaded successfully.")
        
    except Exception as e:
        logger.critical("🔥 Kernel Panic", exc_info=True)
        app.state.is_ready = False
        raise e

    yield
    app.state.is_ready = False
# ═══════════════════════════════════════════════════════════════════════════
# FASTAPI INSTANCE & DTOs
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "Xulcan Agent OS"),
    version="0.4.0-nexus",  # ¡Subimos versión!
    lifespan=lifespan,
)

# 🛡️ Habilitar CORS para que el Dashboard Nexus (Puerto 3000) pueda conectarse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringe esto a tu dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestCorrelationMiddleware)

# 1. ACTUALIZA EL DTO
class RunRequest(BaseModel):
    blueprint_id: str      # 🧠 Qué Agente
    agent_id: str          # 👤 Qué Sesión/Memoria
    input_text: str
    session_key: str | None = None
    metadata: dict | None = None

class RunResponseAsync(BaseModel):
    run_id: str
    status: str
    stream_url: str


# ═══════════════════════════════════════════════════════════════════════════
# AGENT ENDPOINTS (ASYNC FIREHOSE PATTERN)
# ═══════════════════════════════════════════

# 3. LOS NUEVOS ENDPOINTS DE SISTEMA
@app.get("/v1/blueprints", tags=["System"])
async def list_blueprints(request: Request):
    client = request.app.state.client
    return[
        {
            "id": bp.id, "name": bp.name, "provider": bp.model_provider,
            "tools":[t.name if isinstance(t, dict) else t.name for t in bp.tools if getattr(t, 'enabled', True)]
        }
        for bp in client.agent_registry.values()
    ]

@app.post("/v1/blueprints/reload", tags=["System"])
async def reload_blueprints(request: Request):
    count = request.app.state.client.load_blueprints_from_dir("blueprints")
    return {"status": "success", "loaded": count}

@app.post("/v1/agent/run", response_model=RunResponseAsync)
async def run_agent(request: Request, body: RunRequest, background_tasks: BackgroundTasks):
    client: Xulcan = request.app.state.client
    logger = get_logger("run_agent")
    
    # Buscamos el ADN del agente en el nuevo registry
    blueprint = client.agent_registry.get(body.blueprint_id)
    if not blueprint: 
        raise HTTPException(status_code=404, detail=f"Blueprint '{body.blueprint_id}' no encontrado.")
    
    run_id = str(uuid.uuid4())
    
    async def safe_background_run():
        try:
            await client.run(
                prompt=body.input_text,
                blueprint=blueprint,
                agent_id=body.agent_id,       # 👤 Inyectamos la identidad de memoria
                run_id=run_id,
                session_key=body.session_key,
                metadata=body.metadata        # 🗂️ Inyectamos metadatos externos
            )
        except Exception as e:
            logger.error(f"💥💥💥 ERROR CRITICO EN BACKGROUND: {str(e)}", exc_info=True)
            # Tu manejo del EventBus para Nexus (se queda igual)
            if hasattr(client, "event_bus"):
                import json, uuid as err_uuid
                await client.event_bus.publish(
                    f"xulcan:firehose:{run_id}",
                    json.dumps({
                        "id": str(err_uuid.uuid4()), 
                        "type": "run_failed", 
                        "error": str(e)
                    })
                )
                
    background_tasks.add_task(safe_background_run)
    logger.info("🚀 Run dispatched to background", extra={"run_id": run_id, "agent_id": body.agent_id})
    
    # 👇 ¡MANTENEMOS TU RESPUESTA FUERTEMENTE TIPADA! 👇
    return RunResponseAsync(
        run_id=run_id,
        status="running",
        stream_url=f"/v1/runs/{run_id}/stream",
    )


@app.get("/v1/runs/{run_id}/stream")
async def stream_run_events(request: Request, run_id: str):
    """🚀 THE FIREHOSE: Streams events via Server-Sent Events (SSE)."""
    client: Xulcan = request.app.state.client
    
    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. RECUPERACIÓN (Hydration para el UI):
        # Si el usuario refresca la página, le mandamos la historia pasada primero.
        audit = await client.get_audit(run_id)
        if "history" in audit:
            for past_event in audit["history"]:
                yield f"data: {json.dumps(past_event)}\n\n"

        # 2. STREAMING EN TIEMPO REAL:
        try:
            # Escuchamos el bus a través de nuestro cliente
            async for event_json in client.subscribe_to_firehose(run_id):
                # Si el cliente cierra el navegador, cortamos el flujo
                if await request.is_disconnected():
                    break
                    
                # Yield en formato estricto SSE
                yield f"data: {event_json}\n\n"
                
                # Si el agente terminó o falló, cerramos la manguera
                if '"RUN_COMPLETED"' in event_json or '"RUN_FAILED"' in event_json:
                    break
                    
        except asyncio.CancelledError:
            # Cliente canceló la petición (comportamiento normal)
            pass

    # Usamos el media_type "text/event-stream" que es el estándar para SSE
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/v1/runs/{run_id}/audit")
async def get_run_audit(request: Request, run_id: str):
    """Fetch the immutable history and current summary of a run."""
    client: Xulcan = request.app.state.client
    
    result = await client.get_audit(run_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
        
    return result

# 👇 Añade esto junto a tus otros endpoints en mack.py

class HumanResponsePayload(BaseModel):
    approved: bool
    feedback: str = ""

@app.post("/v1/runs/{run_id}/human-response")
async def submit_human_response(run_id: str, payload: HumanResponsePayload):
    from xulcan.governance.human.strategies.api import PENDING_DECISIONS
    # CAMBIO AQUÍ: Importar desde core.contracts (Paso 11)
    from xulcan.governance.verdicts import HumanGateDecision
    # El resultado se mantiene en el base de governance usualmente
    from xulcan.governance.human.base import HumanGateResult 

    # ... resto del código igual ...

    future = PENDING_DECISIONS.get(run_id)
    if not future or future.done():
        raise HTTPException(status_code=404, detail="No hay ninguna petición humana pendiente para este Run.")

    decision = HumanGateDecision.APPROVED if payload.approved else HumanGateDecision.REJECTED
    result = HumanGateResult(decision=decision, feedback=payload.feedback)

    # ¡ESTA LÍNEA DESPIERTA AL KERNEL INMEDIATAMENTE!
    future.set_result(result)
    
    return {"status": "success", "action": "approved" if payload.approved else "rejected"}

# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM ENDPOINTS (Kubernetes & Error Handling)
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