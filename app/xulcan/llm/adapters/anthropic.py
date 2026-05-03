"""Anthropic native LLM adapter."""

from __future__ import annotations
import time
from typing import Any
from pydantic import Field
from anthropic import AsyncAnthropic # Requiere pip install anthropic

from xulcan.core import ExternalID, UsageStats
from xulcan.llm.base import BaseLLMAdapter, BaseLLMConfig
from xulcan.protocol.io import UnifiedResponse, FinishReason

class AnthropicConfig(BaseLLMConfig):
    api_key: ExternalID = Field(description="Anthropic API Key.")

class AnthropicAdapter(BaseLLMAdapter):
    ConfigSchema = AnthropicConfig

    def __init__(self, config: AnthropicConfig):
        super().__init__(config)
        self.client = AsyncAnthropic(api_key=config.api_key)

    async def _generate_impl(self, messages, tools=None, **kwargs) -> UnifiedResponse:
        # Aquí iría la traducción de mensajes similar a lo que hiciste en Gemini
        # Por ahora es un placeholder para que tu estructura esté completa.
        raise NotImplementedError("Anthropic adapter logic pending.")
    

    