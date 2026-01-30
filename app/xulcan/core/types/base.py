"""
Defines the foundational primitives for strict, immutable data modeling.

This module establishes the canonical type system for the core.
Its purpose is to enforce invariants that make higher-level logic
safe, predictable, and economically bounded.

It focuses on three core concerns:

1. Data Integrity
The `CanonicalRecord` base class enforces immutability (frozen instances)
and strict schema validation (no unknown fields), ensuring that once a
state exists, it cannot silently drift or degrade.

2. Defensive Semantic Typing
Specialized string types (`MachineID`, `HumanLabel`,
`SemanticText`, `ExternalID`, `MimeType`, etc.) act as explicit
semantic and security boundaries, preventing malformed, ambiguous,
or adversarial data from entering the system.

3. Resource Accounting
Standardized structures (`UsageStats`, `BudgetConfig`) model execution
costs as conserved physical quantities—tokens and time—and validate
their internal consistency, enabling deterministic budgeting and
auditable execution limits.
"""


from typing import Optional, Annotated
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator
import warnings
import re
import math
import base64
import binascii


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

MAX_IDENTIFIER_LENGTH = 128
"""Maximum allowed length for machine identifiers to prevent database overflow."""

MAX_LABEL_LENGTH = 256
"""Maximum allowed length for human-readable labels."""

MAX_SEMANTIC_TEXT_LENGTH = 10_000_000
"""Maximum allowed length for semantic text content to prevent DoS attacks (10MB)."""

MAX_EXTERNAL_ID_LENGTH = 256
"""Length sufficient for complex provider IDs (e.g., AWS ARNs, long UUIDs)."""

MIME_TYPE_REGEX = re.compile(r'^[a-z0-9\.\-\+]+/[a-z0-9\.\-\+]+(;.*)?$', re.IGNORECASE)
"""Regex for basic MIME type validation (type/subtype). Allows optional parameters."""

ID_REGEX = re.compile(r'^[a-z0-9]([a-z0-9_\-]*[a-z0-9])?$')
"""Regex pattern for validating machine identifiers."""

URL_REGEX = re.compile(
    r'^https?://'                                                    # Scheme
    r'(?:'
        r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}\.?' # Domain (2-63 chars TLD)
        r'|localhost'                                                # Localhost
        r'|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'                       # IPv4
        r'|\[[0-9A-F:]+\]'                                           # IPv6 (Basic, requires brackets)
    r')'
    r'(?::\d+)?'                                                     # Port
    r'(?:/?|[/?]\S+)$',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════════
# BASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalRecord(BaseModel):
    """A base record providing shared configuration for all canonical data structures.

    This abstract base class serves as the foundation for all domain models within
    the core. It enforces strict data validation rules to ensure that data
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
        use_enum_values=False
    )


# ═══════════════════════════════════════════════════════════════════════════
# FLOAT VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _validate_finite_float(v: Optional[float]) -> Optional[float]:
    """Validates that a float value is finite, non-negative, and not NaN.
    
    Args:
        v: The float value to validate.
    
    Returns:
        The validated float value.
    
    Raises:
        ValueError: If the value is NaN, Infinity, or negative.
    """
    if v is None:
        return v
    
    if math.isnan(v):
        raise ValueError("Value cannot be NaN. Must be a valid number.")
    
    if math.isinf(v):
        raise ValueError("Value cannot be Infinity. Must be finite.")
        
    if v < 0:
        raise ValueError("Value cannot be negative.")
        
    return v

# ═══════════════════════════════════════════════════════════════════════════
# FINITE POSITIVE FLOAT TYPE
# ═══════════════════════════════════════════════════════════════════════════

FinitePositiveFloat = Annotated[
    float,
    AfterValidator(_validate_finite_float),
    Field(description="Non-negative, finite floating point value.")
]


# ═══════════════════════════════════════════════════════════════════════════
# STRING NORMALIZATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _validate_machine_identifier(v: str) -> str:    
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
    if v is None:
        return v
    v_stripped = v.strip()
    if not v_stripped:
        raise ValueError("MachineID cannot be empty or whitespace only")
    if len(v_stripped) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"MachineID exceeds maximum length of {MAX_IDENTIFIER_LENGTH} "
            f"characters (got {len(v_stripped)})"
        )
    if not ID_REGEX.match(v_stripped):
        raise ValueError(
            f"Invalid identifier '{v_stripped}'. Must be lowercase, alphanumeric, "
            "and use only '-' or '_' as separators."
        )
    return v_stripped


def _validate_human_label(v: str) -> str:
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
    if v is None:
        return v
    
    # Strip leading/trailing whitespace
    v = v.strip()
    
    if not v:
        raise ValueError("HumanLabel cannot be empty or whitespace only")
    
    # Check for newlines
    if '\n' in v or '\r' in v:
        raise ValueError("HumanLabel must be a single line (no newlines)")
    
    if not v.isprintable():
        raise ValueError(f"HumanLabel contains non-printable characters")
    
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


def _validate_safe_url(v: str) -> str:
    """Validates that a string is a safe, absolute HTTP/HTTPS URL.
    
    Args:
        v: The URL string to validate.
    
    Returns:
        str: The validated URL string.
    
    Raises:
        ValueError: If the URL is empty, a data URI, a relative path, or invalid format.
    """
    if v is None:
        return v
    v = v.strip()
    
    if not v:
        raise ValueError("SafeURL cannot be empty")
    
    # Explicit prevention of Data URIs in the wrong field
    if v.lower().startswith("data:"):
        raise ValueError("Data URIs are not allowed in SafeURL. Use Base64Data instead.")
        
    # Prevention of relative paths (e.g., "/images/logo.png")
    if v.startswith("/"):
        raise ValueError("Relative URLs are not allowed. Must be absolute (http/https).")
        
    if not URL_REGEX.match(v):
        raise ValueError(f"Invalid URL format: '{v}'. Must be absolute HTTP/HTTPS.")
        
    return v


def _validate_base64_data(v: str) -> str:
    """Validates that a string is a valid Base64 encoded payload.
    
    Args:
        v: The Base64 string to validate.
    
    Returns:
        str: The validated and cleaned Base64 string.
    
    Raises:
        ValueError: If the string is empty, contains invalid characters, or is corrupted.
    """
    if v is None:
        return v
    
    # Basic cleaning (ignore spaces/newlines that break strict decoders)
    v_clean = re.sub(r'\s+', '', v)
    
    if not v_clean:
        raise ValueError("Base64Data cannot be empty")
        
    # Verify valid characters (A-Z, a-z, 0-9, +, /, =)
    if not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', v_clean):
        raise ValueError("Invalid Base64 characters detected. Only A-Z, a-z, 0-9, +, / are allowed.")
        
    # Verify actual decoding (structural integrity)
    try:
        # validate=True is important to reject incorrect padding
        base64.b64decode(v_clean, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Corrupt Base64 data: {str(e)}")
        
    return v_clean


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
    if v is None:
        return v
    
    if len(v) > MAX_SEMANTIC_TEXT_LENGTH:
        raise ValueError(
            f"SemanticText exceeds maximum length of {MAX_SEMANTIC_TEXT_LENGTH} "
            f"characters (got {len(v)}). This limit prevents DoS attacks from "
            f"unbounded string payloads."
        )
    
    return v


def _validate_external_id(v: str) -> str:
    """Validates identifiers generated by external providers (Postel's Law).
    
    Accepts a wider range of characters than MachineID but enforces
    safety constraints (printable characters, length).
    
    Args:
        v: The external ID string to validate.
    
    Returns:
        str: The validated external ID string.
    
    Raises:
        ValueError: If the ID is empty, too long, or contains unsafe characters.
    """
    if v is None:
        return v
    v_stripped = v.strip()
    
    if not v_stripped:
        raise ValueError("ExternalID cannot be empty or whitespace only")
        
    if len(v_stripped) > MAX_EXTERNAL_ID_LENGTH:
        raise ValueError(
            f"ExternalID exceeds max length of {MAX_EXTERNAL_ID_LENGTH}"
        )
    
    # Security: Ensure no invisible control characters (NULL bytes, etc.)
    if not v_stripped.isprintable():
        raise ValueError("ExternalID contains unsafe control characters")
        
    return v_stripped


def _validate_mime_type(v: str) -> str:
    """Validates that a string looks like a standard MIME type (type/subtype).
    
    Args:
        v: The MIME type string to validate.
    
    Returns:
        str: The validated MIME type string in lowercase.
    
    Raises:
        ValueError: If the MIME type is empty or has invalid format.
    """
    if v is None:
        return v
    v_stripped = v.strip().lower()  # MIME types are case-insensitive
    
    if not v_stripped:
        raise ValueError("MimeType cannot be empty")
        
    if not MIME_TYPE_REGEX.match(v_stripped):
        raise ValueError(f"Invalid MIME type format: '{v}'. Expected 'type/subtype'.")
        
    return v_stripped


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

MachineID = Annotated[
    str,
    AfterValidator(_validate_machine_identifier),
    Field(description="Machine identifier (stripped, non-empty, max 128 chars)")
]

SafeURL = Annotated[
    str,
    AfterValidator(_validate_safe_url),
    Field(description="Absolute HTTP/HTTPS URL (no data URIs, no relative paths)")
]

Base64Data = Annotated[
    str,
    AfterValidator(_validate_base64_data),
    Field(description="Valid Base64 encoded data string (whitespace stripped)")
]

HumanLabel = Annotated[
    str,
    AfterValidator(_validate_human_label),
    Field(description="Human-readable label (single line, max 256 chars)")
]

SemanticText = Annotated[
    str,
    AfterValidator(_validate_semantic_text),
    Field(description="Raw semantic content (whitespace preserved, max 10MB)")
]


ExternalID = Annotated[
    str,
    AfterValidator(_validate_external_id),
    Field(description="External provider identifier (liberal validation, strict safety)")
]

MimeType = Annotated[
    str,
    AfterValidator(_validate_mime_type),
    Field(description="Standard MIME type string (e.g., 'image/png', 'application/json')")
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

    latency_ms: FinitePositiveFloat = Field(
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
        
        Enforces conservation of time: processing matter (tokens) requires time.
        
        Exception: 100% cache hits (cache_read_input_tokens == input_tokens) with
        zero output tokens may legitimately have near-zero latency.
        
        Note: Finite checks (NaN/Inf) are handled by the field type definition.

        Returns:
            UsageStats: The validated instance.
        """
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

class BudgetExceededError(RuntimeError):
    """Raised when a strict execution limit (HARD_CAP) is breached.
    
    This exception is part of the contract defined by BudgetStrategy.HARD_CAP.
    It indicates that the operation was halted to preserve resources.
    """
    def __init__(self, message: str, current_usage: float, limit: float):
        self.current_usage = current_usage
        self.limit = limit
        super().__init__(f"{message} (Usage: {current_usage} > Limit: {limit})")


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

    time_limit_ms: Optional[FinitePositiveFloat] = Field(
        default=None,
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
        
        For SOFT_NOTIFY without limits, emits a warning since this creates a
        passive observer that tracks but never enforces any constraints.

        Returns:
            BudgetConfig: The validated instance.

        Raises:
            ValueError: If strategy is HARD_CAP but both limits are None.
        
        Warns:
            UserWarning: If strategy is SOFT_NOTIFY but both limits are None.
        """
        if self.strategy == BudgetStrategy.HARD_CAP:
            if self.token_limit is None and self.time_limit_ms is None:
                raise ValueError(
                    "BudgetStrategy.HARD_CAP requires at least one limit "
                    "(token_limit or time_limit_ms) to be defined. "
                    "An unbounded hard cap is semantically meaningless."
                )
        
        if self.strategy == BudgetStrategy.SOFT_NOTIFY:
            if self.is_unbounded:
                warnings.warn(
                    "BudgetConfig with SOFT_NOTIFY and no limits acts as a passive "
                    "observer. It will track resource consumption but never enforce "
                    "constraints. If this is intentional (e.g., for analytics), you "
                    "can safely ignore this warning.",
                    UserWarning,
                    stacklevel=2
                )
        
        return self

    @model_validator(mode='after')
    def validate_positive_time_limit(self) -> 'BudgetConfig':
        """Ensures time limit is greater than zero when specified.
        
        A zero time limit would be logically impossible to satisfy, as any operation
        requires non-zero time to execute.
        
        Returns:
            BudgetConfig: The validated instance.
        
        Raises:
            ValueError: If time_limit_ms is exactly 0.
        """
        if self.time_limit_ms is not None and self.time_limit_ms == 0:
            raise ValueError("time_limit_ms must be greater than 0")
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