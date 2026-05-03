"""Shared validation utilities and constants for the Protocol layer.

This module provides defensive validation functions and configuration constants
used throughout the Protocol package to enforce security boundaries and prevent
attacks like JSON bombs, stack overflow, and resource exhaustion.

Constants:
    MAX_NESTING_DEPTH: Maximum allowed nesting depth for JSON-like structures
        to prevent stack overflow attacks (default: 20 levels).
    MAX_CHUNK_SIZE: Maximum size in bytes for streaming chunks to prevent
        DoS via memory exhaustion (default: 10 MB).

Functions:
    _validate_recursion_depth: Validates that data structures don't exceed
        maximum nesting depth, protecting against maliciously crafted payloads.
"""

from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Maximum allowed nesting depth for JSON-like structures.
MAX_NESTING_DEPTH = 20
MAX_CHUNK_SIZE = 10_000_000  # 10 MB
