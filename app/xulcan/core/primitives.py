"""
Defines the foundational primitives for strict, immutable data modeling.

This module establishes the canonical type system for the core.
Its purpose is to provide the atomic building blocks and security boundaries
for the domain.

It focuses on two core concerns:

1. Data Integrity
The `ImmutableRecord` base class enforces immutability (frozen instances)
and strict schema validation (no unknown fields), ensuring that once a
state exists, it cannot silently drift or degrade.

2. Defensive Semantic Typing
Specialized string types (`MachineID`, `DisplayName`,
`SemanticText`, `ExternalID`, `MimeType`, etc.) act as explicit
semantic and security boundaries, preventing malformed, ambiguous,
or adversarial data from entering the system.
"""

from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, AfterValidator
import re
import math
import json
import base64
import binascii


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

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

SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*)?$")
"""Regex for validating semantic versioning strings (e.g., '1.0.0', '2.1.0-beta')."""

CONTEXT_KEY_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
"""Regex for validating context variable names (must be valid Python identifiers)."""

MAX_NESTING_DEPTH = 20
"""Maximum allowed nesting depth for JSON-like structures to prevent stack overflow."""


# =============================================================================
# BASE CONFIGURATION
# =============================================================================

class ImmutableRecord(BaseModel):
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
        >>> class MyConfig(ImmutableRecord):
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


# =============================================================================
# FLOAT VALIDATION HELPERS
# =============================================================================

def _validate_finite_float(value: float) -> float:
    """Validates that a float value is finite, non-negative, and not NaN.

    Args:
        value: The float value to validate.

    Returns:
        The validated float value.

    Raises:
        ValueError: If the value is NaN, Infinity, or negative.
    """
    if math.isnan(value):
        raise ValueError("Value cannot be NaN. Must be a valid number.")

    if math.isinf(value):
        raise ValueError("Value cannot be Infinity. Must be finite.")

    if value < 0.0:
        raise ValueError("Value cannot be negative.")

    return value


# =============================================================================
# FINITE POSITIVE FLOAT TYPE
# =============================================================================

FinitePositiveFloat = Annotated[
    float,
    AfterValidator(_validate_finite_float),
    Field(description="Non-negative, finite floating point value.")
]


# =============================================================================
# STRING NORMALIZATION HELPERS
# =============================================================================

def _validate_machine_identifier(value: str) -> str:
    """Validates and normalizes a machine identifier string.

    Enforces that the string is not empty or whitespace-only after stripping,
    and prevents DoS attacks by enforcing maximum length constraints.

    Args:
        value: The input string to validate.

    Returns:
        The stripped identifier string.

    Raises:
        ValueError: If the string is empty, contains only whitespace, or exceeds
                    the maximum allowed length.
    """
    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError("MachineID cannot be empty or whitespace-only.")

    if len(cleaned_value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"MachineID exceeds maximum length of {MAX_IDENTIFIER_LENGTH} "
            f"characters (got {len(cleaned_value)})."
        )

    if not ID_REGEX.match(cleaned_value):
        raise ValueError(
            f"Invalid identifier '{cleaned_value}'. Must be lowercase, alphanumeric, "
            "and use only hyphens ('-') or underscores ('_') as separators."
        )

    return cleaned_value


def _validate_display_name(value: str) -> str:
    """Validates and normalizes a human-readable UI label.

    Enforces that the string is not empty, contains no newline characters,
    and does not exceed length limits. Also filters invisible control characters
    that could break UI rendering or JSON logs.

    Args:
        value: The input string to validate.

    Returns:
The stripped, single-line label.

    Raises:
        ValueError: If the string is empty, whitespace-only, contains newlines,
                    contains invisible control characters, or exceeds maximum length.
    """
    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError("DisplayName cannot be empty or whitespace-only.")

    if '\n' in cleaned_value or '\r' in cleaned_value:
        raise ValueError("DisplayName must be a single line (no newlines).")

    if not cleaned_value.isprintable():
        raise ValueError("DisplayName contains non-printable characters.")

    # Check for additional invisible control characters (ASCII 0-31 except space)
    # This prevents tabs, vertical tabs, backspaces, etc.
    control_chars = [c for c in cleaned_value if ord(c) < 32 and c not in ('\n', '\r')]
    if control_chars:
        raise ValueError(
            f"DisplayName contains invisible control characters: "
            f"{[hex(ord(c)) for c in control_chars]}"
        )

    # Enforce stricter length limit for user-facing labels
    if len(cleaned_value) > MAX_LABEL_LENGTH:
        raise ValueError(
            f"DisplayName exceeds maximum length of {MAX_LABEL_LENGTH} "
            f"characters (got {len(cleaned_value)})."
        )

    return cleaned_value


def _validate_safe_url(value: str) -> str:
    """Validates that a string is a safe, absolute HTTP/HTTPS URL.

    Args:
        value: The URL string to validate.

    Returns:
        The validated URL string.

    Raises:
        ValueError: If the URL is empty, a data URI, a relative path, or invalid format.
    """
    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError("SafeURL cannot be empty.")

    # Explicit prevention of Data URIs in the wrong field
    if cleaned_value.lower().startswith("data:"):
        raise ValueError("Data URIs are not allowed in SafeURL. Use Base64Data instead.")

    # Prevention of relative paths (e.g., "/images/logo.png")
    if cleaned_value.startswith("/"):
        raise ValueError("Relative URLs are not allowed. Must be absolute (http/https).")

    if not URL_REGEX.match(cleaned_value):
        raise ValueError(f"Invalid URL format: '{cleaned_value}'. Must be absolute HTTP/HTTPS.")

    return cleaned_value


def _validate_base64_data(value: str) -> str:
    """Validates that a string is a valid Base64 encoded payload.

    Args:
        value: The Base64 string to validate.

    Returns:
        The validated and cleaned Base64 string.

    Raises:
        ValueError: If the string is empty, contains invalid characters, or is corrupted.
    """
    # Basic cleaning (ignore spaces/newlines that break strict decoders)
    cleaned_value = re.sub(r'\s+', '', value)

    if not cleaned_value:
        raise ValueError("Base64Data cannot be empty.")

    # Verify valid characters (A-Z, a-z, 0-9, +, /, =)
    if not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', cleaned_value):
        raise ValueError("Invalid Base64 characters detected. Only A-Z, a-z, 0-9, +, / and = are allowed.")

    # Verify actual decoding (structural integrity)
    try:
        # validate=True is important to reject incorrect padding
        base64.b64decode(cleaned_value, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Corrupt Base64 data: {str(e)}")

    return cleaned_value


def _validate_semantic_text(value: str) -> str:
    """Validates semantic text content to prevent DoS attacks.

    Enforces maximum length constraints to prevent memory exhaustion attacks
    from unbounded string payloads. Semantic text is typically used for prompts,
    code, or other content where whitespace preservation is critical.

    Args:
        value: The input string to validate.

    Returns:
        The validated semantic text string.

    Raises:
        ValueError: If the string exceeds the maximum allowed length.
    """
    if len(value) > MAX_SEMANTIC_TEXT_LENGTH:
        raise ValueError(
            f"SemanticText exceeds maximum length of {MAX_SEMANTIC_TEXT_LENGTH} "
            f"characters (got {len(value)}). This limit prevents DoS attacks from "
            f"unbounded string payloads."
        )

    return value


def _validate_external_id(value: str) -> str:
    """Validates identifiers generated by external providers (Postel's Law).

    Accepts a wider range of characters than MachineID but enforces
    safety constraints (printable characters, length).

    Args:
        value: The external ID string to validate.

    Returns:
        The validated external ID string.

    Raises:
        ValueError: If the ID is empty, too long, or contains unsafe characters.
    """
    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError("ExternalID cannot be empty or whitespace-only.")

    if len(cleaned_value) > MAX_EXTERNAL_ID_LENGTH:
        raise ValueError(
            f"ExternalID exceeds max length of {MAX_EXTERNAL_ID_LENGTH}."
        )

    # Security: Ensure no invisible control characters (NULL bytes, etc.)
    if not cleaned_value.isprintable():
        raise ValueError("ExternalID contains unsafe control characters.")

    return cleaned_value


def _validate_mime_type(value: str) -> str:
    """Validates that a string looks like a standard MIME type (type/subtype).

    Args:
        value: The MIME type string to validate.

    Returns:
        The validated MIME type string in lowercase.

    Raises:
        ValueError: If the MIME type is empty or has invalid format.
    """
    # Preserve original case here; callers may enforce exact-case policies.
    cleaned_value = value.strip().lower()

    if not cleaned_value:
        raise ValueError("MimeType cannot be empty.")

    if not MIME_TYPE_REGEX.match(cleaned_value):
        raise ValueError(f"Invalid MIME type format: '{value}'. Expected 'type/subtype'.")

    return cleaned_value


def _validate_semver(value: str) -> str:
    """Validates Semantic Versioning (Major.Minor.Patch[-PreRelease]).

    Args:
        value: The version string to validate.

    Returns:
        The validated semver string.

    Raises:
        ValueError: If the format does not match semantic versioning specification.
    """
    cleaned_value = value.strip()
    if not SEMVER_REGEX.match(cleaned_value):
        raise ValueError(f"Invalid Semantic Version format: '{cleaned_value}'. Expected MAJOR.MINOR.PATCH.")
    return cleaned_value


def _validate_context_key(value: str) -> str:
    """Validates a key used for programmatic context/memory storage.

    Args:
        value: The context key string to validate.

    Returns:
        The validated context key string.

    Raises:
        ValueError: If the key exceeds 64 characters or is not a valid identifier.
    """
    cleaned_value = value.strip()

    if len(cleaned_value) > 64:
        raise ValueError("ContextKey exceeds maximum length of 64characters.")

    if not CONTEXT_KEY_REGEX.match(cleaned_value):
        raise ValueError(
            f"Invalid ContextKey '{cleaned_value}'. "
            "Must be a valid programmatic identifier (letters, numbers, underscores)."
        )
    return cleaned_value


def _validate_json_dict(value: dict[str, Any]) -> dict[str, Any]:
    """Validates that a dictionary is strictly JSON-serializable and depth-bounded.

    Args:
        value: The dictionary to validate.

    Returns:
        The validated dictionary.

    Raises:
        ValueError: If the value is not a dictionary, is not JSON-serializable,
                    or exceeds the maximum nesting depth.
    """
    if not isinstance(value, dict):
        raise ValueError("Payload must be a dictionary.")

    # 1. Validate physical serialization (Prevents DB objects, lambdas, non-serializable types)
    try:
        json.dumps(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Payload must be strictly JSON-serializable: {e}")

    # 2. Validate recursive depth (Prevents JSON bombs / YAML aliases)
    def _check_depth(data: Any, current_depth: int = 0) -> None:
        if current_depth > MAX_NESTING_DEPTH:
            raise ValueError(
                f"Data structure exceeds maximum nesting depth of {MAX_NESTING_DEPTH}."
            )

        if isinstance(data, dict):
            for val in data.values():
                _check_depth(val, current_depth + 1)
        elif isinstance(data, list):
            for item in data:
                _check_depth(item, current_depth + 1)

    _check_depth(value)
    return value


# =============================================================================
# SEMANTIC PRIMITIVES
# =============================================================================

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

DisplayName = Annotated[
    str,
    AfterValidator(_validate_display_name),
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

SemanticVersion = Annotated[
    str,
    AfterValidator(_validate_semver),
    Field(description="Semantic version string (e.g., '1.0.0', '2.1.0-beta')")
]

ContextKey = Annotated[
    str,
    AfterValidator(_validate_context_key),
    Field(description="Safe programmatic key for state/memory storage")
]

JsonDict = Annotated[
    dict[str, Any],
    AfterValidator(_validate_json_dict),
    Field(description="A strictly JSON-serializable dictionary with bounded nesting depth.")
]
