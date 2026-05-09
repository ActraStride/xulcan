# xulcan/runtime/llm_registry_adapter.py
"""Transitional compatibility bridge between topology-driven runtime and legacy LLMExecutor.

Removed once LLMExecutor becomes topology-native in Issue 5+.
"""

from __future__ import annotations

import logging
from typing import Any, List

from xulcan.llm.base import BaseLLMAdapter

logger = logging.getLogger("xulcan.runtime.llm_registry_adapter")


class RuntimeLLMRegistryAdapter:
    """Exposes a registry-like .build() interface over already-instantiated LLM adapters.

    LLMExecutor expects:
        registry.build(provider_name, params) -> BaseLLMAdapter

    ResolvedInfrastructure already contains:
        llm_instances: dict[str, BaseLLMAdapter]

    This bridge satisfies the LLMExecutor contract without modifying it.
    params are intentionally ignored — adapters were configured at materialization time.

    Transitional: disappears when LLMExecutor is refactored in Issue 5+.
    """

    def __init__(self, instances: dict[str, BaseLLMAdapter]):
        self._instances = instances
        logger.debug(
            f"RuntimeLLMRegistryAdapter initialized: {list(instances.keys())}"
        )

    def build(self, name: str, params: dict[str, Any]) -> BaseLLMAdapter:
        if name not in self._instances:
            raise ValueError(
                f"LLM instance '{name}' not found in runtime topology. "
                f"Available: {list(self._instances.keys())}"
            )
        return self._instances[name]

    @property
    def available_providers(self) -> List[str]:
        return list(self._instances.keys())
