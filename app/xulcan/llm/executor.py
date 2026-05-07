"""LLM Executor — The Router and Fallback Orchestrator for Models."""

from __future__ import annotations
import json
import logging
from typing import Any

from xulcan.registry import ProviderRegistry
from xulcan.llm.base import BaseLLMAdapter
from xulcan.llm.exceptions import TransientLLMError, FatalLLMError
from xulcan.blueprint.schema import AgentBlueprint, ModelSpec
from xulcan.protocol.message import UnifiedMessage
from xulcan.protocol.io import UnifiedResponse
from xulcan.protocol.tools import ToolDefinition

logger = logging.getLogger("xulcan.llm.executor")

class LLMExecutor:
    """Orchestrates LLM generation, managing lifecycle, caching, and fallbacks."""

    def __init__(self, registry: ProviderRegistry[BaseLLMAdapter]):
        self.registry = registry
        self._adapter_cache: dict[str, BaseLLMAdapter] = {}

    def _get_adapter(self, spec: ModelSpec):
        """
        Traductor: Convierte un ModelSpec de la Ontología en el 
        diccionario plano que el Registry y los Adapters esperan.
        """
        # 1. Recuperamos el caché si existe
        cache_key = f"{spec.provider}:{spec.name}:{spec.temperature}"
        if cache_key in self._adapter_cache:
            return self._adapter_cache[cache_key]

        # 2. Preparamos los parámetros para el adaptador viejo
        # Aquí es donde resolvemos el error de 'model_name missing' de Gemini
        adapter_params = dict(spec.params) # Traemos los extras (top_p, etc.)
        adapter_params["model_name"] = spec.name
        adapter_params["temperature"] = spec.temperature
        
        if spec.max_tokens:
            adapter_params["max_tokens"] = spec.max_tokens

        # 3. Construimos vía Registry
        adapter = self.registry.build(spec.provider, adapter_params)
        
        # 4. Guardamos en caché y retornamos
        self._adapter_cache[cache_key] = adapter
        return adapter

    async def generate(
        self, 
        blueprint: AgentBlueprint, 
        messages: list[UnifiedMessage], 
        tools: list[ToolDefinition] | None = None, 
        **kwargs: Any
    ) -> UnifiedResponse:
        """Executes generation with automatic multi-model fallback routing."""
        
        # 1. Construimos la cadena usando los objetos ModelSpec directamente
        # Esto nos da acceso a .name, .provider, .temperature, etc.
        specs: list[ModelSpec] = [blueprint.model] + blueprint.fallbacks

        fallback_history = []

        # 2. Bucle de intentos
        for i, spec in enumerate(specs):
            provider_name = spec.provider  # Ahora es un atributo del objeto
            try:
                # ✅ Llamamos pasando el objeto completo (2 argumentos: self y spec)
                adapter = self._get_adapter(spec)
                
                response = await adapter.generate(messages=messages, tools=tools, **kwargs)
                
                # Inyectamos metadatos de éxito
                response.provider_metadata["actual_provider"] = provider_name
                response.provider_metadata["actual_model"] = spec.name
                
                if i > 0:
                    response.provider_metadata["fallback_triggered"] = True
                    response.provider_metadata["fallback_history"] = fallback_history
                
                return response
                
            except TransientLLMError as e:
                fallback_history.append({
                    "failed_provider": provider_name,
                    "model_name": spec.name, # Acceso directo al objeto
                    "reason": str(e)
                })
                
                if i < len(specs) - 1:
                    logger.warning(f"🔄 LLM Fallback: {provider_name} failed. Trying next...")
                    continue
                raise e 
                
            except FatalLLMError as e:
                logger.error(f"💀 LLM Fatal Error in {provider_name}: {e}. Aborting.")
                raise e 

        raise RuntimeError("LLM Chain exhausted without response or clear error.")