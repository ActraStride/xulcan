"""Adapter for GitHub Models API (Azure AI Inference)."""

from __future__ import annotations
from pydantic import Field
from xulcan.core import ExternalID, SafeURL
from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter, OpenAICompatibleConfig

class GitHubModelsConfig(OpenAICompatibleConfig):
    """Configuration for GitHub Models."""
    base_url: SafeURL | None = Field(
        default="https://models.inference.ai.azure.com",
        description="GitHub Models (Azure AI) endpoint."
    )
    

class GitHubModelsAdapter(OpenAICompatibleAdapter):
    """Adapter for GitHub's free-tier model hosting."""
    ConfigSchema = GitHubModelsConfig

    def __init__(self, config: GitHubModelsConfig):
        super().__init__(config)