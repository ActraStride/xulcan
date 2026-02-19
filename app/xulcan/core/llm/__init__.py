"""LLM integration layer."""

from .client import (
    BaseLLMClient,
    LLMAuthenticationError,
    LLMClientFactory,
    LLMProviderError,
    LLMResponse,
    LLMValidationError,
)
from .base import BaseLLMAdapter
from .fallback import AllFallbacksFailedError, FallbackClient, FallbackOption
from .adapters import AnthropicAdapter, BaseAdapter, GeminiAdapter, OpenAIAdapter

__all__ = [
    "BaseLLMAdapter",
    "BaseLLMClient",
    "FallbackClient",
    "FallbackOption",
    "AllFallbacksFailedError",
    "LLMAuthenticationError",
    "LLMProviderError",
    "LLMValidationError",
    "LLMClientFactory",
    "LLMResponse",
    "BaseAdapter",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
]
