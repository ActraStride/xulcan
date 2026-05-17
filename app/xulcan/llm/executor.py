"""LLM Executor — The Router and Fallback Orchestrator for Models."""

from __future__ import annotations
import logging
from typing import Any

from xulcan.llm.base import BaseLLMAdapter
from xulcan.llm.exceptions import TransientLLMError, FatalLLMError
from xulcan.blueprint.schema import AgentBlueprint, ModelSpec
from xulcan.protocol.message import UnifiedMessage
from xulcan.protocol.io import UnifiedResponse
from xulcan.protocol.tools import ToolDefinition

logger = logging.getLogger("xulcan.llm.executor")

class LLMExecutor:
    """Orchestrates LLM generation, managing fallbacks and runtime-bound adapters."""

    def __init__(self, instances: dict[str, BaseLLMAdapter]):
        self._instances = instances

    def _get_adapter(self, spec: ModelSpec) -> BaseLLMAdapter:
        if spec.provider not in self._instances:
            raise ValueError(
                f"LLM instance '{spec.provider}' not found in runtime topology. "
                f"Available: {list(self._instances.keys())}"
            )
        return self._instances[spec.provider]

    @staticmethod
    def _build_inference_kwargs(spec: ModelSpec, kwargs: dict[str, Any]) -> dict[str, Any]:
        inference_kwargs = dict(kwargs)
        inference_kwargs.update(spec.params)
        inference_kwargs["model_name"] = spec.name
        inference_kwargs["temperature"] = spec.temperature
        inference_kwargs["max_tokens"] = spec.max_tokens
        return inference_kwargs

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
                adapter = self._get_adapter(spec)
                inference_kwargs = self._build_inference_kwargs(spec, kwargs)
                response = await adapter.generate(
                    messages=messages,
                    tools=tools,
                    **inference_kwargs,
                )

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