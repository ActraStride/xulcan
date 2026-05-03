"""Adapter for Groq's lightning-fast LPU inference engine."""

from __future__ import annotations

from pydantic import Field

from xulcan.core import ExternalID, SafeURL
from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter, OpenAICompatibleConfig


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class GroqConfig(OpenAICompatibleConfig):
    """Configuration for Groq's LPU inference engine.
    
    Inherits api_key, temperature, and max_tokens from OpenAICompatibleConfig.
    Hardwires the Groq base_url — the developer never needs to set it.
    """
    
    base_url: SafeURL | None = Field(
        default="https://api.groq.com/openai/v1",
        description="Groq API endpoint (hardwired, not user-configurable)."
    )
    
  


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class GroqAdapter(OpenAICompatibleAdapter):
    """Adapter for Groq's lightning-fast LPU inference engine.
    
    Inherits all OpenAI-protocol logic from OpenAICompatibleAdapter.
    Only specialization: Groq's base_url and default model.
    """

    ConfigSchema = GroqConfig

    def __init__(self, config: GroqConfig):
        super().__init__(config)