"""Shared data models used by different LLM providers.

Naming convention note:
- We use short names (`Message`, `Response`, `ToolSpec`) to keep things
  beginner-friendly.
- We intentionally keep a single naming style to avoid confusion.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolUse(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    call_id: Optional[str] = None


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str
    tool_calls: List[ToolUse] = Field(default_factory=list)
    tool_call_id: Optional[str] = None


class Response(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = ""
    tool_calls: List[ToolUse] = Field(default_factory=list)
    usage: Optional[TokenUsage] = None
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
