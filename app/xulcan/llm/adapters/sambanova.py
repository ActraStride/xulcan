"""Adapter for SambaNova Cloud API."""

from __future__ import annotations
from pydantic import Field
from xulcan.core import ExternalID, SafeURL
from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter, OpenAICompatibleConfig

class SambaNovaConfig(OpenAICompatibleConfig):
    """Configuration for SambaNova Cloud."""
    base_url: SafeURL | None = Field(
        default="https://api.sambanova.ai/v1",
        description="SambaNova API endpoint."
    )
   

class SambaNovaAdapter(OpenAICompatibleAdapter):
    """Adapter for SambaNova's fast LPU inference."""
    ConfigSchema = SambaNovaConfig

    def __init__(self, config: SambaNovaConfig):
        super().__init__(config)