"""Level 0 Fixtures: Core Primitives & Economics.

These fixtures are available to ALL submodules (core, protocol, blueprint, kernel).
"""

import pytest
from enum import Enum
from typing import Type

from xulcan.core import CanonicalRecord, UsageStats, BudgetConfig, BudgetStrategy

# ═══════════════════════════════════════════════════════════════════════════
# PRIMITIVES (DATA TYPES)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_machine_id() -> str:
    """A valid, safe identifier for testing ID validation."""
    return "valid_machine_id_v1"

@pytest.fixture
def valid_safe_url() -> str:
    """A secure, absolute HTTPS URL."""
    return "https://api.xulcan.io/v1/resource"

@pytest.fixture
def valid_base64_data() -> str:
    """Valid Base64 string (Hello World)."""
    return "SGVsbG8gV29ybGQ="

@pytest.fixture
def dummy_record_class() -> Type[CanonicalRecord]:
    """Provides a concrete implementation of CanonicalRecord for testing inheritance."""
    class DummyRecord(CanonicalRecord):
        name: str
        value: int = 0
    return DummyRecord

@pytest.fixture
def dummy_enum() -> Type[Enum]:
    """Provides a test enum for serialization validation."""
    class TestStatus(str, Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"
    return TestStatus

# ═══════════════════════════════════════════════════════════════════════════
# ECONOMICS (MONEY & TIME)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_usage_stats() -> UsageStats:
    """Provides a valid UsageStats instance with consistent math."""
    return UsageStats(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,  # 100 + 50
        cache_read_input_tokens=30,
        cache_creation_input_tokens=20,
        latency_ms=1200.0
    )

@pytest.fixture
def valid_budget() -> BudgetConfig:
    """Provides a valid BudgetConfig instance."""
    return BudgetConfig(
        token_limit=1000,
        time_limit_ms=5000.0,
        strategy=BudgetStrategy.HARD_CAP
    )