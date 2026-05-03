# --- START OF FILE huggingface.py ---

"""Adapter for Hugging Face Serverless Inference API."""

from __future__ import annotations

from pydantic import Field

from xulcan.core import ExternalID, SafeURL
from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter, OpenAICompatibleConfig


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class HuggingFaceConfig(OpenAICompatibleConfig):
    """Configuration for Hugging Face Inference API.
    
    Inherits api_key, temperature, and max_tokens from OpenAICompatibleConfig.
    Hardwires the HF base_url.
    """
    
    base_url: SafeURL | None = Field(
        default="https://api-inference.huggingface.co/v1/",
        description="Hugging Face OpenAI-compatible endpoint."
    )
    
    


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class HuggingFaceAdapter(OpenAICompatibleAdapter):
    """Adapter for Hugging Face Serverless Inference API.
    
    Provides access to thousands of open-source models for free.
    Inherits all OpenAI-protocol logic from OpenAICompatibleAdapter.
    """

    ConfigSchema = HuggingFaceConfig

    def __init__(self, config: HuggingFaceConfig):
        super().__init__(config)

# --- END OF FILE huggingface.py ---