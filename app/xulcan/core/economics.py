"""
Defines the economic primitives for resource accounting in Xulcan.

This module models the consumption of resources as conserved physical
quantities — Matter (tokens) and Time (latency).

Strictly contains: UsageStats.

Budget enforcement policies (BursarHaltError, EnforcedBursarConfig, etc.)
live in xulcan/governance/ — they are policy concerns, not physics.
"""

from __future__ import annotations

import warnings
from pydantic import Field, model_validator

from .primitives import ImmutableRecord, FinitePositiveFloat


# =============================================================================
# TOKEN USAGE TRACKING
# =============================================================================

class UsageStats(ImmutableRecord):
    """Represents the tangible consumption of resources (Matter & Time) for an operation.

    This class tracks the two fundamental economic units of the system:
    1. **Information (Tokens):** The raw material processed by the model.
    2. **Duration (Latency):** The execution time consumed by the system.

    It enforces mathematical consistency for token counts and serves as the
    standard currency for budgeting, billing, and observability.

    Cache Semantics:
        - 0 means "no cache used" or "provider doesn't support caching".
        - For observability, 0 is preferred over None to simplify aggregation.

    Aggregation Behavior:
        - When adding two instances (`stats1 + stats2`), token counts are summed.
        - **Latency is also summed**, assuming sequential execution. Parallel
        orchestration logic should handle time aggregation separately if needed.

    Attributes:
        input_tokens: Number of tokens in the input prompt.
        output_tokens: Number of tokens in the generated response.
        total_tokens: Total tokens processed (must equal input + output).
        cache_read_input_tokens: Input tokens served from cache.
        cache_creation_input_tokens: Input tokens used to populate cache.
        latency_ms: Wall-clock execution time in milliseconds.

    Raises:
        ValueError: If input_tokens + output_tokens != total_tokens.
        ValueError: If cache_read_input_tokens > input_tokens.
        ValueError: If latency_ms is NaN or Infinity.

    Example:
        >>> stats = UsageStats(
        ...     input_tokens=100,
        ...     output_tokens=50,
        ...     total_tokens=150,
        ...     latency_ms=1200.0
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

    latency_ms: FinitePositiveFloat = Field(
        description="Wall-clock execution time in milliseconds."
    )

    @classmethod
    def zero(cls) -> UsageStats:
        """Initializes an empty usage record.

        Returns:
            UsageStats: A new instance with all counters set to zero.
        """
        return cls(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            latency_ms=0.0
        )

    def __add__(self, other: UsageStats) -> UsageStats:
        """Aggregates two UsageStats objects.

        Allows for the summation of usage statistics across multiple calls
        or usage sessions.

        Args:
            other: The UsageStats object to add to the current instance.

        Returns:
            UsageStats: A new instance representing the sum of both records.

        Raises:
            TypeError: If the 'other' object is not an instance of UsageStats.
        """
        if not isinstance(other, UsageStats):
            return NotImplemented

        return UsageStats(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            latency_ms=self.latency_ms + other.latency_ms
        )

    @model_validator(mode='after')
    def validate_token_math(self) -> UsageStats:
        """Ensures the token counts are mathematically consistent.

        Validates that total_tokens equals input_tokens + output_tokens.

        Returns:
            UsageStats: The validated instance.

        Raises:
            ValueError: If total_tokens does not equal input + output.
        """
        calculated = self.input_tokens + self.output_tokens
        if self.total_tokens != calculated:
            raise ValueError(
                f"Token math mismatch: "
                f"input({self.input_tokens}) + output({self.output_tokens}) "
                f"= {calculated}, but total_tokens={self.total_tokens}"
            )
        return self

    @model_validator(mode='after')
    def validate_cache_consistency(self) -> UsageStats:
        """Ensures cache read tokens do not exceed total input tokens.

        Returns:
            UsageStats: The validated instance.

        Raises:
            ValueError: If cache_read_input_tokens exceeds input_tokens.
        """
        if self.cache_read_input_tokens > self.input_tokens:
            raise ValueError(
                f"Cache read tokens ({self.cache_read_input_tokens}) cannot exceed "
                f"total input tokens ({self.input_tokens})"
            )
        return self

    @model_validator(mode='after')
    def validate_latency_plausibility(self) -> UsageStats:
        """Validates physical plausibility of resource consumption.

        Warns if tokens were processed with zero latency, unless it was a
        full cache hit. This enforces the conservation of time principle.

        Returns:
            UsageStats: The validated instance.
        """
        if self.total_tokens == 0:
            return self

        is_full_cache_hit = (
            self.cache_read_input_tokens == self.input_tokens
            and self.output_tokens == 0
        )

        if self.latency_ms == 0 and not is_full_cache_hit:
            warnings.warn(
                f"Physical inconsistency: processed {self.total_tokens} tokens "
                f"with 0.0ms latency. This violates conservation of time unless "
                f"the operation was 100% cached.",
                UserWarning,
                stacklevel=2
            )

        return self

    @property
    def is_empty(self) -> bool:
        """Checks if this usage record represents zero consumption.

        Returns:
            True if both total_tokens and latency_ms are zero, False otherwise.
        """
        return self.total_tokens == 0 and self.latency_ms == 0.0

    @property
    def cache_efficiency(self) -> float:
        """Calculates the percentage of input tokens served from cache.

        Returns:
            The ratio of cache_read_input_tokens to input_tokens,
            or 0.0 if input_tokens is zero.
        """
        if self.input_tokens == 0:
            return 0.0
        return self.cache_read_input_tokens / self.input_tokens

    @property
    def total_cache_tokens(self) -> int:
        """Calculates total cache-related tokens (both read and creation).

        Returns:
            The sum of cache_read_input_tokens and cache_creation_input_tokens.
        """
        return self.cache_read_input_tokens + self.cache_creation_input_tokens
