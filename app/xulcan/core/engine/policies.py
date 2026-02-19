"""Orchestration policies and guardrails."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class OrchestrationPolicy(BaseModel):
    max_iterations: int = 5
    max_depth: int = 2
    max_cost_usd: Optional[float] = None
    allow_models: Optional[List[str]] = None
    deny_models: Optional[List[str]] = None
