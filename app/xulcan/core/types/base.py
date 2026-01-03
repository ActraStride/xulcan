"""Defines the foundational primitives for strict, immutable data modeling.

This module establishes the root type system, enforcing data integrity and 
predictability across the library. It focuses on three core concerns:

1. Data Integrity: The `CanonicalRecord` base class enforces immutability 
   (frozen instances) and strict schema validation (no unknown fields).
2. Semantic Typing: Specialized string types (`CanonicalIdentifier`, `HumanLabel`) 
   to distinguish between internal IDs and user-facing content.
3. Resource Accounting: Standardized structures (`UsageStats`, `BudgetConfig`) 
   to track and limit the fundamental costs of execution: Information (Tokens) 
   and Time (Latency).
"""

from typing import Optional, Annotated
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# BASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalRecord(BaseModel):
    """A base record providing shared configuration for all canonical data structures.

    This abstract base class serves as the foundation for all domain models within
    the library. It enforces strict data validation rules to ensure that data
    passing through the system is immutable and predictable.

    Configuration Behaviors:
        - **Immutability (frozen=True):** Instances cannot be modified after creation. 
          This makes them thread-safe and hashable.
        - **Strictness (extra='forbid'):** The model will raise a validation error 
          if unknown fields are provided. This prevents silent failures caused by 
          typos or outdated API responses.

    Example:
        >>> class MyConfig(CanonicalRecord):
        ...     name: str
        ...
        >>> conf = MyConfig(name="test")
        >>> conf.name = "changed"  # Raises ValidationError (Frozen)
        >>> conf = MyConfig(name="test", bad_field=1)  # Raises ValidationError (Extra)
    """
    model_config = ConfigDict(
        frozen=True,
        extra='forbid',
    )


# ═══════════════════════════════════════════════════════════════════════════
# STRING NORMALIZATION LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def _validate_identifier(v: str) -> str:    
    """Validates and normalizes a machine identifier string.

    Enforces that the string is not empty or whitespace-only after stripping.

    Args:
        v: The input string to validate.

    Returns:
        str: The stripped identifier string.

    Raises:
        ValueError: If the string is empty or contains only whitespace.
    """
    if v is None:
        return v
    v_stripped = v.strip()
    if not v_stripped:
        raise ValueError("CanonicalIdentifier cannot be empty or whitespace only")
    return v_stripped


def _validate_single_line(v: str) -> str:
    """Validates and normalizes a human-readable UI label.

    Enforces that the string is not empty and contains no newline characters.

    Args:
        v: The input string to validate.

    Returns:
        str: The stripped, single-line label.

    Raises:
        ValueError: If the string is empty, whitespace-only, or contains newlines.
    """
    v = _validate_identifier(v)
    if '\n' in v or '\r' in v:
        raise ValueError("HumanLabel must be a single line (no newlines)")
    return v


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

CanonicalIdentifier = Annotated[
    str,
    AfterValidator(_validate_identifier),
    Field(description="Machine identifier (stripped, non-empty)")
]

HumanLabel = Annotated[
    str,
    AfterValidator(_validate_single_line),
    Field(description="Human-readable label (single line)")
]

SemanticText = Annotated[
    str,
    Field(description="Raw semantic content (whitespace preserved)")
]


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN USAGE TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class UsageStats(CanonicalRecord):
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
    
    Example:
        >>> stats = UsageStats(
        ...     input_tokens=100,
        ...     output_tokens=50,
        ...     total_tokens=150,
        ...     latency_ms=1200
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

    latency_ms: int = Field(
        default=0,
        ge=0,
        description="Wall-clock execution time in milliseconds."
    )

    @classmethod
    def zero(cls) -> "UsageStats":
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
            latency_ms=0
        )

    def __add__(self, other: "UsageStats") -> "UsageStats":
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
    def validate_token_math(self) -> 'UsageStats':
        """Ensures the token counts are mathematically consistent.
        
        This validation catches provider bugs where reported token counts do not 
        aggregate correctly, which has been observed in production with various 
        LLM providers.

        Returns:
            UsageStats: The validated instance.

        Raises:
            ValueError: If input + output != total.
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
    def validate_cache_consistency(self) -> 'UsageStats':
        """Ensures cache read tokens do not exceed total input tokens.
        
        It is logically impossible to read more tokens from the cache than 
        were present in the input prompt.

        Returns:
            UsageStats: The validated instance.

        Raises:
            ValueError: If cache_read_input_tokens > input_tokens.
        """
        if self.cache_read_input_tokens > self.input_tokens:
            raise ValueError(
                f"Cache read tokens ({self.cache_read_input_tokens}) cannot exceed "
                f"total input tokens ({self.input_tokens})"
            )
        return self
    
    @property
    def cache_efficiency(self) -> float:
        """Calculates the percentage of input tokens served from cache.
        
        Returns:
            float: A value between 0.0 and 1.0 representing the cache hit ratio.
                   Returns 0.0 if no input tokens exist or cache was not used.
        
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
        """Calculates total cache-related tokens (both read and creation).
        
        This metric is useful for cost calculations when providers charge 
        differently for cache write vs. cache read operations.
        
        Returns:
            int: The sum of cache_read_input_tokens and cache_creation_input_tokens.
        """
        return self.cache_read_input_tokens + self.cache_creation_input_tokens


# ═══════════════════════════════════════════════════════════════════════════
# ECONOMIC PRIMITIVES (BUDGETING)
# ═══════════════════════════════════════════════════════════════════════════

class BudgetStrategy(str, Enum):
    """Defines the behavior policy when a resource limit is reached.
    
    This enumeration dictates whether the system should forcefully abort operations
    or simply flag them for review when a budget threshold is crossed.

    Attributes:
        HARD_CAP: Immediately terminates the execution path (raises BudgetExceededError).
                  Typically used for autonomous agents (scrapers, workers) to prevent loops.
        SOFT_NOTIFY: Allows execution to continue but flags the run (e.g., logs a warning).
                     Typically used for critical paths or VIP requests where completion is priority.
    """
    HARD_CAP = "hard_cap"
    SOFT_NOTIFY = "soft_notify"


class BudgetConfig(CanonicalRecord):
    """Defines the economic constraints (Resource Limits) for an execution run.

    This class represents the "A Priori" contract (Input Constraints) enforced by 
    the system, as opposed to `UsageStats` which represents the "A Posteriori" 
    report (Output Costs).

    It decouples policy from identity, allowing dynamic budget assignment per request. 
    Limits can be set on **Matter** (Tokens) and/or **Time** (Latency).

    Attributes:
        token_limit: Maximum allowed total tokens (input + output). If None, 
                     unbounded (provider limits still apply).
        time_limit_ms: Maximum allowed execution duration in milliseconds. If None,
                       unbounded (though server timeouts may apply).
        strategy: Enforcement policy (Strict vs. Passive) triggered when EITHER limit is hit.
        cost_center: Optional ledger tag (e.g., 'client_a', 'internal_ops') for 
                     billing analytics and cost attribution.

    Example:
        >>> budget = BudgetConfig(
        ...     token_limit=1000,
        ...     time_limit_ms=5000,
        ...     strategy=BudgetStrategy.HARD_CAP,
        ...     cost_center="campaign_january"
        ... )
    """
    token_limit: Optional[int] = Field(
        default=None,
        gt=0,
        description="Hard limit on total tokens. If None, no limit is enforced."
    )
    
    time_limit_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Hard limit on total execution time (latency). If None, no limit is enforced."
    )

    strategy: BudgetStrategy = Field(
        default=BudgetStrategy.HARD_CAP,
        description="Policy to apply when the limit is reached."
    )

    cost_center: Optional[str] = Field(
        default=None,
        description="Optional tag to track who 'pays' for this budget (for analytics)."
    )

    @model_validator(mode='after')
    def validate_configuration(self) -> 'BudgetConfig':
        """Validates that the configuration is logical.
        
        While a 'None' token_limit with a HARD_CAP strategy is technically valid 
        (implying an infinite budget until the provider's physical limit is hit), 
        it is logically redundant. This validator ensures basic consistency and
        serves as a hook for future complex validation (e.g., USD limits).

        Returns:
            BudgetConfig: The validated instance.
        """
        return self