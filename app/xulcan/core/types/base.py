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
import warnings
import re
import math


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

MAX_IDENTIFIER_LENGTH = 128
"""Maximum allowed length for machine identifiers to prevent database overflow."""

MAX_LABEL_LENGTH = 256
"""Maximum allowed length for human-readable labels."""

MAX_SEMANTIC_TEXT_LENGTH = 10_000_000
"""Maximum allowed length for semantic text content to prevent DoS attacks (10MB)."""

ID_REGEX = re.compile(r'^[a-z0-9]([a-z0-9_\-]*[a-z0-9])?$')
"""Regex pattern for validating machine identifiers."""


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

    Enforces that the string is not empty or whitespace-only after stripping,
    and prevents DoS attacks by enforcing maximum length constraints.

    Args:
        v: The input string to validate.

    Returns:
        str: The stripped identifier string.

    Raises:
        ValueError: If the string is empty, contains only whitespace, or exceeds 
                    the maximum allowed length.
    """
    if v is None: # pragma: no cover
        return v
    v_stripped = v.strip()
    if not v_stripped:
        raise ValueError("CanonicalIdentifier cannot be empty or whitespace only")
    if len(v_stripped) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"CanonicalIdentifier exceeds maximum length of {MAX_IDENTIFIER_LENGTH} "
            f"characters (got {len(v_stripped)})"
        )
    if not ID_REGEX.match(v_stripped):
        raise ValueError(
            f"Invalid identifier '{v_stripped}'. Must be lowercase, alphanumeric, "
            "and use only '-' or '_' as separators."
        )
    return v_stripped


def _validate_single_line(v: str) -> str:
    """Validates and normalizes a human-readable UI label.

    Enforces that the string is not empty, contains no newline characters,
    and does not exceed length limits. Also filters invisible control characters
    that could break UI rendering or JSON logs.

    Args:
        v: The input string to validate.

    Returns:
        str: The stripped, single-line label.

    Raises:
        ValueError: If the string is empty, whitespace-only, contains newlines,
                    contains invisible control characters, or exceeds maximum length.
    """

    # Early exit for None
    if v is None: # pragma: no cover
        return v
    
    # Strip leading/trailing whitespace
    v = v.strip()
    
    if not v: # pragma: no cover
        raise ValueError("HumanLabel cannot be empty or whitespace only")
    
    # Check for newlines
    if '\n' in v or '\r' in v:
        raise ValueError("HumanLabel must be a single line (no newlines)")
    
    # Check for additional invisible control characters (ASCII 0-31 except space)
    # This prevents tabs, vertical tabs, backspaces, etc.
    control_chars = [c for c in v if ord(c) < 32 and c not in ('\n', '\r')]
    if control_chars:
        raise ValueError(
            f"HumanLabel contains invisible control characters: "
            f"{[hex(ord(c)) for c in control_chars]}"
        )
    
    # Enforce stricter length limit for user-facing labels
    if len(v) > MAX_LABEL_LENGTH:
        raise ValueError(
            f"HumanLabel exceeds maximum length of {MAX_LABEL_LENGTH} "
            f"characters (got {len(v)})"
        )
    
    return v


def _validate_semantic_text(v: str) -> str:
    """Validates semantic text content to prevent DoS attacks.

    Enforces maximum length constraints to prevent memory exhaustion attacks
    from unbounded string payloads. Semantic text is typically used for prompts,
    code, or other content where whitespace preservation is critical.

    Args:
        v: The input string to validate.

    Returns:
        str: The validated semantic text string.

    Raises:
        ValueError: If the string exceeds the maximum allowed length.
    """
    if v is None: # pragma: no cover
        return v
    
    if len(v) > MAX_SEMANTIC_TEXT_LENGTH:
        raise ValueError(
            f"SemanticText exceeds maximum length of {MAX_SEMANTIC_TEXT_LENGTH} "
            f"characters (got {len(v)}). This limit prevents DoS attacks from "
            f"unbounded string payloads."
        )
    
    return v


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

CanonicalIdentifier = Annotated[
    str,
    AfterValidator(_validate_identifier),
    Field(description="Machine identifier (stripped, non-empty, max 128 chars)")
]

HumanLabel = Annotated[
    str,
    AfterValidator(_validate_single_line),
    Field(description="Human-readable label (single line, max 256 chars)")
]

SemanticText = Annotated[
    str,
    AfterValidator(_validate_semantic_text),
    Field(description="Raw semantic content (whitespace preserved, max 10MB)")
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

    latency_ms: float = Field(
        ge=0.0,
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
            latency_ms=0.0
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
    
    @model_validator(mode='after')
    def validate_latency_plausibility(self) -> 'UsageStats':
        """Validates physical plausibility of resource consumption.
        
        Enforces two critical invariants:
        1. Latency must be a finite, valid number (not NaN or Infinity).
        2. Warns if tokens were processed but no latency was recorded, which violates
           the physical constraint that processing matter (tokens) requires time.
        
        Exception: 100% cache hits (cache_read_input_tokens == input_tokens) with
        zero output tokens may legitimately have near-zero latency.

        Returns:
            UsageStats: The validated instance.
        
        Raises:
            ValueError: If latency_ms is NaN or Infinity.
        """
        # Critical: reject exotic floating point values that would corrupt aggregation
        if math.isnan(self.latency_ms):
            raise ValueError(
                f"Latency cannot be NaN. This indicates a calculation error in "
                f"upstream timing logic. Allowing NaN would contaminate all "
                f"aggregated metrics."
            )
        
        if math.isinf(self.latency_ms):
            raise ValueError(
                f"Latency cannot be Infinity. This indicates a calculation error "
                f"or timeout handling issue in upstream timing logic."
            )
        
        # Skip plausibility check if no processing occurred
        if self.total_tokens == 0:
            return self
        
        # Check if this is a full cache hit with no generation
        is_full_cache_hit = (
            self.cache_read_input_tokens == self.input_tokens 
            and self.output_tokens == 0
        )
        
        # Warn if we processed tokens but recorded no time (unless full cache hit)
        if self.latency_ms == 0 and not is_full_cache_hit:
            warnings.warn(
                f"Physical inconsistency: processed {self.total_tokens} tokens "
                f"with 0ms latency. This violates conservation of time unless "
                f"the operation was 100% cached.",
                UserWarning
            )
        
        return self
    
    @property
    def is_empty(self) -> bool:
        """Checks if this usage record represents zero consumption.
        
        Useful for logging systems to filter out noise from no-op operations.
        
        Returns:
            bool: True if both tokens and latency are zero.
        
        Example:
            >>> stats = UsageStats.zero()
            >>> stats.is_empty
            True
        """
        return self.total_tokens == 0 and self.latency_ms == 0
    
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

    Example:
        >>> budget = BudgetConfig(
        ...     token_limit=1000,
        ...     time_limit_ms=5000,
        ...     strategy=BudgetStrategy.HARD_CAP
        ... )
    """
    token_limit: Optional[int] = Field(
        default=None,
        gt=0,
        description="Hard limit on total tokens. If None, no limit is enforced."
    )
    
    time_limit_ms: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Hard limit on total execution time (latency). If None, no limit is enforced."
    )

    strategy: BudgetStrategy = Field(
        default=BudgetStrategy.HARD_CAP,
        description="Policy to apply when the limit is reached."
    )

    @model_validator(mode='after')
    def validate_strategy_semantics(self) -> 'BudgetConfig':
        """Prevents "toothless watchdog" configurations.
        
        A HARD_CAP strategy without any defined limits is logically meaningless
        and likely indicates a configuration error. This validator enforces that
        at least one resource constraint exists when hard enforcement is requested.

        Returns:
            BudgetConfig: The validated instance.

        Raises:
            ValueError: If strategy is HARD_CAP but both limits are None.
        """
        if self.strategy == BudgetStrategy.HARD_CAP:
            if self.token_limit is None and self.time_limit_ms is None:
                raise ValueError(
                    "BudgetStrategy.HARD_CAP requires at least one limit "
                    "(token_limit or time_limit_ms) to be defined. "
                    "An unbounded hard cap is semantically meaningless."
                )
        return self
    
    @model_validator(mode='after')
    def validate_time_limit_finiteness(self) -> 'BudgetConfig':
        """Ensures time limits are physically plausible values.
        
        Rejects NaN or Infinity in time_limit_ms to prevent runtime errors during
        budget enforcement logic. Budget comparisons (usage < limit) would fail
        silently with exotic floating point values.

        Returns:
            BudgetConfig: The validated instance.
        
        Raises:
            ValueError: If time_limit_ms is NaN or Infinity.
        """
        if self.time_limit_ms is not None:
            if math.isnan(self.time_limit_ms):
                raise ValueError(
                    f"time_limit_ms cannot be NaN. Budget enforcement requires "
                    f"finite, comparable values."
                )
            
            if math.isinf(self.time_limit_ms):
                raise ValueError(
                    f"time_limit_ms cannot be Infinity. Use None for unbounded "
                    f"time limits instead."
                )
        
        return self
    
    @property
    def is_unbounded(self) -> bool:
        """Checks if this budget imposes no resource constraints.
        
        Useful for the Kernel to optimize away budget checking logic when
        no limits are actually enforced.
        
        Returns:
            bool: True if both token_limit and time_limit_ms are None.
        
        Example:
            >>> budget = BudgetConfig(strategy=BudgetStrategy.SOFT_NOTIFY)
            >>> budget.is_unbounded
            True
        """
        return self.token_limit is None and self.time_limit_ms is None