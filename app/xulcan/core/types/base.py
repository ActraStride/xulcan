"""Defines canonical data structures for a generative model abstraction layer.

This module provides a set of Pydantic models that create a standardized,
provider-agnostic interface for interacting with various generative models.
It includes robust and type-safe definitions for token usage tracking and
base configuration for all domain models.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# BASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalModel(BaseModel):
    """A base model providing shared configuration for all canonical data structures.

    This class enforces immutability (`frozen=True`) and prevents unknown fields
    (`extra='forbid'`), ensuring that all data structures are strict and predictable.
    
    Configuration:
        frozen: Prevents modification after creation (immutability for predictability).
        extra: Rejects unknown fields to prevent data pollution from providers.
        str_strip_whitespace: Normalizes string inputs automatically.
    """
    model_config = ConfigDict(
        frozen=True,
        extra='forbid',
        str_strip_whitespace=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN USAGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class UsageStats(CanonicalModel):
    """Represents token usage statistics for a model interaction.

    Includes details for both standard token counts and caching metrics. The model
    enforces that `input_tokens` + `output_tokens` equals `total_tokens`.
    
    Cache Semantics:
        - 0 means "no cache used" or "provider doesn't support caching"
        - For observability purposes, 0 is sufficient (no need for None)
        - Providers without cache support simply return 0 for cache fields

    Attributes:
        input_tokens: The number of tokens in the input prompt.
        output_tokens: The number of tokens in the generated response.
        total_tokens: The total number of tokens processed (must equal input + output).
        cache_read_input_tokens: Number of input tokens served from cache (0 if no cache).
        cache_creation_input_tokens: Number of input tokens used to populate cache (0 if no cache).
    
    Raises:
        ValueError: If input_tokens + output_tokens != total_tokens
    
    Example:
        >>> stats = UsageStats(
        ...     input_tokens=100,
        ...     output_tokens=50,
        ...     total_tokens=150,
        ...     cache_read_input_tokens=30
        ... )
        >>> stats.total_tokens
        150
    """
    input_tokens: int = Field(
        ge=0,
        description="Number of tokens in the prompt."
    )
    
    output_tokens: int = Field(
        ge=0,
        description="Number of tokens in the generated response."
    )
    
    total_tokens: int = Field(
        ge=0,
        description="Total tokens processed (input + output)."
    )
    
    cache_read_input_tokens: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of input tokens served from cache. "
            "0 if no cache hit or provider doesn't support caching."
        )
    )
    
    cache_creation_input_tokens: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of input tokens used to create a new cache entry. "
            "0 if no cache created or provider doesn't support caching."
        )
    )

    @model_validator(mode='after')
    def validate_token_math(self) -> 'UsageStats':
        """Ensure the token counts are mathematically consistent.
        
        This validation catches provider bugs where token counts don't add up,
        which has been observed in production with various LLM providers.
        
        Raises:
            ValueError: If input + output != total
        """
        calculated = self.input_tokens + self.output_tokens
        if self.total_tokens != calculated:
            raise ValueError(
                f"Token math mismatch: "
                f"input({self.input_tokens}) + output({self.output_tokens}) "
                f"= {calculated}, but total_tokens={self.total_tokens}"
            )
        return self
    
    @property
    def cache_efficiency(self) -> float:
        """Calculate the percentage of input tokens served from cache.
        
        Returns:
            Float between 0.0 and 1.0 representing cache hit ratio.
            Returns 0.0 if no input tokens or cache not used.
        
        Example:
            >>> stats = UsageStats(input_tokens=100, output_tokens=50, 
            ...                    total_tokens=150, cache_read_input_tokens=30)
            >>> stats.cache_efficiency
            0.3
        """
        if self.input_tokens == 0:
            return 0.0
        return self.cache_read_input_tokens / self.input_tokens
    
    @property
    def total_cache_tokens(self) -> int:
        """Total cache-related tokens (both read and creation).
        
        Useful for cost calculations when providers charge differently
        for cache operations.
        
        Returns:
            Sum of cache_read_input_tokens and cache_creation_input_tokens
        """
        return self.cache_read_input_tokens + self.cache_creation_input_tokens