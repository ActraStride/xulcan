"""Ring 0 — Xulcan System Tools.

Privileged tools for internal state manipulation and event orchestration.
These tools have direct access to the SystemEnvironment and the current Run ID.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from xulcan.tools.base import BaseToolExecutor
from xulcan.protocol.tools import ToolCall, ToolDefinition, FunctionDef
from xulcan.protocol.message import ToolMessage
from xulcan.kernel.environment import SystemEnvironment

logger = logging.getLogger("xulcan.tools.stdlib.system")

class SystemToolExecutor(BaseToolExecutor):
    """Ring 0 Executor: Provides privileged access to Memory and EventBus."""

    def __init__(self, environment: SystemEnvironment) -> None:
        self.environment = environment
        
        # Definiciones de herramientas (Esquemas para el LLM)
        self._definitions = {
            "_set_memory": ToolDefinition(
                function=FunctionDef(
                    name="_set_memory",
                    description="Guarda un valor en la memoria de corto/largo plazo del agente.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "Nombre de la variable."},
                            "value": {"type": "string", "description": "Contenido a guardar (string o JSON)."}
                        },
                        "required": ["key", "value"]
                    }
                )
            ),
            "_publish_event": ToolDefinition(
                function=FunctionDef(
                    name="_publish_event",
                    description="Emite un evento al bus del sistema para notificar a otros agentes.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Canal del evento (ej: 'status/task_done')."},
                            "message": {"type": "string", "description": "Cuerpo del mensaje."}
                        },
                        "required": ["channel", "message"]
                    }
                )
            )
        }

    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        return [self._definitions[n] for n in tool_names if n in self._definitions]

    async def execute(self, call: ToolCall) -> ToolMessage:
        ctx = call.context or {}
        run_id = ctx.get("run_id")
        
        if not run_id:
            return ToolMessage(call.id, call.name, '{"error": "Security Breach: No run_id provided"}')

        try:
            if call.name == "_set_memory":
                key = call.arguments["key"]
                val = call.arguments["value"]
                await self.environment.state_store.set(run_id, key, val)
                return ToolMessage(call.id, call.name, f"✅ Key '{key}' saved.")

            elif call.name == "_publish_event":
                if not self.environment.event_bus:
                    return ToolMessage(call.id, call.name, '{"error": "EventBus not configured"}')
                
                channel = call.arguments["channel"]
                msg = call.arguments["message"]
                await self.environment.event_bus.publish(channel, msg)
                return ToolMessage(call.id, call.name, f"✅ Event published to '{channel}'.")

            raise ValueError(f"Unknown System Tool: {call.name}")

        except Exception as e:
            logger.error(f"💥 Ring 0 Error ({call.name}): {e}")
            return ToolMessage(call.id, call.name, json.dumps({"error": str(e)}))