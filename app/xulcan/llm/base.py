"""Base class and config contract for all LLM adapters.

ConfigSchema Pattern:
    Every adapter defines its own ConfigSchema(BaseLLMConfig).
    The adapter's __init__ receives a validated config instance, never **kwargs.
    The Registry uses AdapterClass.ConfigSchema to validate before instantiation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pydantic import Field

from xulcan.core.primitives import (
    ImmutableRecord,
    ExternalID,
    FinitePositiveFloat,
)
from xulcan.protocol.message import UnifiedMessage
from xulcan.protocol.io import UnifiedResponse
from xulcan.protocol.tools import ToolDefinition


# ═══════════════════════════════════════════════════════════════════════════
# BASE CONFIG (Universal LLM Parameters)
# ═══════════════════════════════════════════════════════════════════════════

class BaseLLMConfig(ImmutableRecord):
    """Universal parameters that every LLM adapter must declare.
    
    These are cognitive parameters — they affect how the agent *thinks*.
    They belong in the Blueprint (soul), not in app.py (body).
    
    Provider-specific parameters (api_key, host, org_id) are declared
    in each adapter's own ConfigSchema subclass.
    
    Note: api_key and credentials are intentionally NOT here.
    They belong in VaultStore / app.py infrastructure.
    """
    model_name: ExternalID = Field(
        description="Specific model identifier (e.g., 'gemini-2.5-flash', 'llama3')."
    )
    
    temperature: FinitePositiveFloat = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0 = deterministic, 2.0 = creative)."
    )
    
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Hard limit on output tokens (None = provider default)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# BASE ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class BaseLLMAdapter(ABC):
    """Abstract base class for LLM providers.
    
    Contract:
        - Every subclass MUST declare ConfigSchema: type[BaseLLMConfig]
        - __init__ receives a validated config instance, never raw dicts.
        - The Template Method pattern delegates execution to _generate_impl.
    
    Deliberately does NOT inherit LLMProvider (Protocol).
    Duck typing handles structural compatibility.
    The Kernel depends on the Protocol. Adapters depend on this ABC.
    These are two completely separate architectural concerns.
    """

    # Subclasses MUST override this with their specific config class
    ConfigSchema: type[BaseLLMConfig] = BaseLLMConfig

    def __init__(self, config: BaseLLMConfig):
        self.config = config

    async def generate(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> UnifiedResponse:
        """Template method. Delegates to provider-specific _generate_impl.
        
        Note: model, temperature, and max_tokens come from self.config, 
        not as parameters here. The adapter is already configured at 
        construction time by the Registry.
        """
        return await self._generate_impl(
            messages=messages,
            tools=tools,
            **kwargs
        )

    @abstractmethod
    async def _generate_impl(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None,
        **kwargs: Any,
    ) -> UnifiedResponse:
        """Provider-specific implementation. Uses self.config for all parameters."""
        pass