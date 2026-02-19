"""API schemas for orchestration requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OrchestrationPolicyRequest(BaseModel):
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_depth: int = Field(default=2, ge=1, le=5)
    max_cost_usd: Optional[float] = Field(default=None, ge=0)
    allow_models: Optional[List[str]] = None
    deny_models: Optional[List[str]] = None


class ModelSpecRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    system_prompt: Optional[str] = None
    tools: List[str] = []
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)


class OrchestrateRequest(BaseModel):
    input: str = Field(..., min_length=1)
    core_model: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    models: Optional[List[ModelSpecRequest]] = None
    tools: Optional[List[str]] = None
    policy: Optional[OrchestrationPolicyRequest] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    system_prompt: Optional[str] = None
    custom_instructions: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ToolCallRecord(BaseModel):
    tool: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


class OrchestrateResponse(BaseModel):
    output: str
    tool_calls: List[ToolCallRecord] = []
    usage: Optional[Dict[str, Any]] = None
