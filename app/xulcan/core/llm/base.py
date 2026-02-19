"""Base LLM interface for provider adapters.

This is the common contract all providers should follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Type

from pydantic import BaseModel

from xulcan.core.types import Message, Response, ToolSpec


class BaseLLMAdapter(ABC):
    """One shared interface for all LLM providers.

    Naming convention note:
    - This interface uses simple shared model names (`Message`, `Response`,
      `ToolSpec`) for readability.
    - We keep one naming style only.
    """

    def __init__(self, model_name: str, api_key: str, **kwargs) -> None:
        self.model_name = model_name
        self.api_key = api_key
        self.extra = kwargs

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSpec]] = None,
        output_schema: Optional[Type[BaseModel]] = None,
    ) -> Response:
        """Generate one model response using the shared internal format."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return a token estimate/count for plain text."""
