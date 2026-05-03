"""Adapter for DeepSeek Cloud API."""

from __future__ import annotations
from pydantic import Field
from xulcan.core import ExternalID, SafeURL
from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter, OpenAICompatibleConfig

class DeepSeekConfig(OpenAICompatibleConfig):
    """Configuration for DeepSeek Cloud."""
    base_url: SafeURL | None = Field(
        default="https://api.deepseek.com",
        description="DeepSeek API endpoint."
    )
class DeepSeekAdapter(OpenAICompatibleAdapter):
    """Adapter for DeepSeek's high-efficiency models."""
    ConfigSchema = DeepSeekConfig

    def __init__(self, config: DeepSeekConfig):
        super().__init__(config)