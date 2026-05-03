"""Property-based testing for Xulcan's economics type system.

This module validates mathematical invariants, resource accounting, and
numerical stability using Hypothesis fuzzing strategies. Tests focus on:

- UsageStats algebraic laws (associativity, commutativity, conservation)
- BudgetConfig logical consistency
- Cache coherence and physics constraints
- Aggregation monotonicity
- Floating-point precision stability
- Serialization roundtrips

Test Philosophy:
    Property-based testing validates that invariants hold universally across
    the input space, rather than testing specific examples.

References:
    - Master Fuzzing Plan: "Xulcan Core Types v1.0"
    - Unit tests: test_base.py (specific regression cases)
"""

import pytest
import json
import math
from typing import Set
from hypothesis import given, strategies as st, settings
from pydantic import ValidationError

from xulcan.core import (
    UsageStats,
    BudgetConfig,
    BudgetStrategy
)


# ═══════════════════════════════════════════════════════════════════════════
# HYPOTHESIS STRATEGY GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

@st.composite
def valid_usage_stats(draw) -> UsageStats:
    """Generates mathematically consistent UsageStats instances.
    
    Ensures token counts satisfy conservation law: total = input + output.
    Generates values from zero to astronomical numbers (10M tokens).
    
    Returns:
        UsageStats: A valid instance with consistent token arithmetic.
    """
    input_tokens = draw(st.integers(min_value=0, max_value=10_000_000))
    output_tokens = draw(st.integers(min_value=0, max_value=10_000_000))
    total_tokens = input_tokens + output_tokens
    
    # Cache tokens must be <= input tokens (physical constraint)
    cache_read = draw(st.integers(min_value=0, max_value=input_tokens))
    cache_creation = draw(st.integers(min_value=0, max_value=input_tokens))
    
    # Latency must be finite and non-negative
    latency_ms = draw(st.floats(
        min_value=0.0, 
        max_value=1e6, 
        allow_nan=False, 
        allow_infinity=False
    ))
    
    return UsageStats(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
        latency_ms=latency_ms
    )


@st.composite
def valid_budget_config(draw) -> BudgetConfig:
    """Generates logically valid BudgetConfig instances.
    
    Ensures HARD_CAP strategies always have at least one defined limit.
    Generates both bounded and unbounded configurations.
    
    Returns:
        BudgetConfig: A valid configuration respecting strategy semantics.
    """
    strategy = draw(st.sampled_from(BudgetStrategy))
    
    # For HARD_CAP, ensure at least one limit exists
    if strategy == BudgetStrategy.HARD_CAP:
        has_token_limit = draw(st.booleans())
        has_time_limit = draw(st.booleans())
        
        # Ensure at least one is True
        if not (has_token_limit or has_time_limit):
            has_token_limit = True
        
        token_limit = draw(st.integers(min_value=1, max_value=1_000_000)) if has_token_limit else None
        time_limit_ms = draw(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False)) if has_time_limit else None
    else:
        # SOFT_NOTIFY can have any combination (including both None)
        token_limit = draw(st.none() | st.integers(min_value=1, max_value=1_000_000))
        time_limit_ms = draw(st.none() | st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    
    return BudgetConfig(
        token_limit=token_limit,
        time_limit_ms=time_limit_ms,
        strategy=strategy
    )


# ═══════════════════════════════════════════════════════════════════════════
# USAGE STATS MATHEMATICAL PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestUsageStatsMath:
    """Property-based tests for UsageStats algebraic laws and physics.
    
    Validates that UsageStats behaves as a commutative monoid under addition:
    - Associativity: (A + B) + C = A + (B + C)
    - Commutativity: A + B = B + A
    - Identity: A + 0 = A
    - Conservation: total = input + output (always)
    - Cache coherence: cache_read ≤ input (physical constraint)
    - Monotonicity: aggregation never decreases totals
    """
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_conservation_law_universally(self, stats1: UsageStats, stats2: UsageStats):
        """Invariant: total_tokens = input_tokens + output_tokens under all aggregations."""
        result = stats1 + stats2
        assert result.total_tokens == result.input_tokens + result.output_tokens
    
    @given(a=valid_usage_stats(), b=valid_usage_stats(), c=valid_usage_stats())
    @settings(max_examples=300)
    def test_associativity_universally(self, a: UsageStats, b: UsageStats, c: UsageStats):
        """Law: addition is associative, (A + B) + C ≡ A + (B + C) for all triples."""
        left_assoc = (a + b) + c
        right_assoc = a + (b + c)
        
        assert left_assoc.total_tokens == right_assoc.total_tokens
        assert left_assoc.input_tokens == right_assoc.input_tokens
        assert left_assoc.output_tokens == right_assoc.output_tokens
        assert math.isclose(left_assoc.latency_ms, right_assoc.latency_ms, rel_tol=1e-9)
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_commutativity_universally(self, stats1: UsageStats, stats2: UsageStats):
        """Law: addition is commutative, A + B ≡ B + A for all pairs."""
        left = stats1 + stats2
        right = stats2 + stats1
        
        assert left.total_tokens == right.total_tokens
        assert left.input_tokens == right.input_tokens
        assert left.output_tokens == right.output_tokens
        assert math.isclose(left.latency_ms, right.latency_ms, rel_tol=1e-9)
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=500)
    def test_zero_is_additive_identity(self, stats: UsageStats):
        """Law: zero is the additive identity, A + 0 ≡ A for all stats."""
        zero = UsageStats.zero()
        result = stats + zero
        
        assert result.total_tokens == stats.total_tokens
        assert result.input_tokens == stats.input_tokens
        assert result.output_tokens == stats.output_tokens
        assert math.isclose(result.latency_ms, stats.latency_ms, rel_tol=1e-9)
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_cache_coherence_preserved_under_addition(self, stats1: UsageStats, stats2: UsageStats):
        """Constraint: cache_read ≤ input holds after aggregation."""
        result = stats1 + stats2
        assert result.cache_read_input_tokens <= result.input_tokens
        assert result.cache_creation_input_tokens <= result.input_tokens

    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=1000)
    def test_addition_prevents_overflow_to_infinity(self, stats1: UsageStats, stats2: UsageStats):
        """Constraint: latency remains finite or raises controlled error on overflow."""
        try:
            result = stats1 + stats2
            assert math.isfinite(result.latency_ms), "Latency overflowed to Infinity"
        except ValueError as e:
            # It is acceptable to fail if result is infinite, 
            # but it must be our controlled ValueError, not a raw float exception
            assert "cannot be Infinity" in str(e)
    
    @given(
        input_tokens=st.integers(min_value=1, max_value=10_000),
        output_tokens=st.integers(min_value=0, max_value=10_000),
        overflow=st.integers(min_value=1, max_value=1000)
    )
    @settings(max_examples=200)
    def test_cache_read_cannot_exceed_input(self, input_tokens: int, output_tokens: int, overflow: int):
        """Constraint: cache_read ≤ input (cannot read more than sent)."""
        with pytest.raises(ValidationError, match="Cache read tokens"):
            UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cache_read_input_tokens=input_tokens + overflow,
                latency_ms=100.0
            )
    
    @given(
        input_tokens=st.integers(min_value=0, max_value=10_000),
        output_tokens=st.integers(min_value=0, max_value=10_000),
        cache_ratio=st.floats(min_value=0.0, max_value=1.0)
    )
    @settings(max_examples=200)
    def test_cache_efficiency_bounded_by_unity(self, input_tokens: int, output_tokens: int, cache_ratio: float):
        """Invariant: cache efficiency ∈ [0, 1] for all valid configurations."""
        cache_read = int(input_tokens * cache_ratio)
        
        stats = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cache_read_input_tokens=cache_read,
            latency_ms=100.0
        )
        
        assert 0.0 <= stats.cache_efficiency <= 1.0
    
    @given(
        input_tokens=st.integers(min_value=1, max_value=10_000),
        output_tokens=st.integers(min_value=0, max_value=10_000)
    )
    @settings(max_examples=200)
    def test_full_cache_hit_is_physically_valid(self, input_tokens: int, output_tokens: int):
        """Property: 100% cache hit (cache_read = input) is valid."""
        stats = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cache_read_input_tokens=input_tokens,  # Full hit
            latency_ms=10.0  # Near-zero latency acceptable for cache hits
        )
        
        assert stats.cache_efficiency == 1.0
        assert stats.cache_read_input_tokens == stats.input_tokens
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_addition_never_decreases_totals(self, stats1: UsageStats, stats2: UsageStats):
        """Property: addition is monotonic, (A + B).total ≥ max(A.total, B.total)."""
        result = stats1 + stats2
        assert result.total_tokens >= stats1.total_tokens
        assert result.total_tokens >= stats2.total_tokens
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_addition_never_decreases_latency(self, stats1: UsageStats, stats2: UsageStats):
        """Property: latency is monotonic under sequential aggregation."""
        result = stats1 + stats2
        assert result.latency_ms >= stats1.latency_ms
        assert result.latency_ms >= stats2.latency_ms
    
    @given(stats1=valid_usage_stats(), stats2=valid_usage_stats())
    @settings(max_examples=500)
    def test_addition_preserves_non_negativity(self, stats1: UsageStats, stats2: UsageStats):
        """Invariant: all fields remain non-negative after aggregation."""
        result = stats1 + stats2
        assert result.input_tokens >= 0
        assert result.output_tokens >= 0
        assert result.total_tokens >= 0
        assert result.cache_read_input_tokens >= 0
        assert result.cache_creation_input_tokens >= 0
        assert result.latency_ms >= 0.0


# ═══════════════════════════════════════════════════════════════════════════
# USAGE STATS RESILIENCE PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestUsageStatsResilience:
    """Property-based tests for UsageStats numerical stability and persistence.
    
    Validates:
    - NaN/Infinity rejection
    - Floating-point precision preservation
    - JSON serialization roundtrips
    - Hash stability
    - Immutability enforcement
    """
    
    @given(
        input_tokens=st.integers(min_value=0, max_value=1000),
        output_tokens=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=100)
    def test_nan_latency_always_rejected(self, input_tokens: int, output_tokens: int):
        """Property: NaN latency is universally rejected."""
        with pytest.raises(ValidationError, match="cannot be NaN"):
            UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=math.nan
            )
    
    @given(
        input_tokens=st.integers(min_value=0, max_value=1000),
        output_tokens=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=100)
    def test_infinity_latency_always_rejected(self, input_tokens: int, output_tokens: int):
        """Property: infinite latency is universally rejected."""
        with pytest.raises(ValidationError, match="cannot be Infinity"):
            UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=math.inf
            )
    
    @given(
        input_tokens=st.integers(min_value=0, max_value=1000),
        output_tokens=st.integers(min_value=0, max_value=1000),
        latency_ms=st.floats(
            min_value=0.001,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False
        )
    )
    @settings(max_examples=500)
    def test_latency_precision_preserved_in_json(self, input_tokens: int, output_tokens: int, latency_ms: float):
        """Property: latency survives JSON roundtrip with relative error < 1e-9."""
        stats = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms
        )
        
        json_str = stats.model_dump_json()
        recovered = UsageStats.model_validate_json(json_str)
        
        assert math.isclose(recovered.latency_ms, stats.latency_ms, rel_tol=1e-9)
    
    @given(
        latency_ms=st.floats(
            min_value=0.0,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False
        )
    )
    @settings(max_examples=200)
    def test_zero_latency_survives_serialization(self, latency_ms: float):
        """Property: zero and near-zero latency values roundtrip exactly."""
        stats = UsageStats(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms
        )
        
        json_str = stats.model_dump_json()
        recovered = UsageStats.model_validate_json(json_str)
        
        if latency_ms == 0.0:
            assert recovered.latency_ms == 0.0
        else:
            assert math.isclose(recovered.latency_ms, latency_ms, rel_tol=1e-9)
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=500)
    def test_usage_stats_json_roundtrip_perfect_fidelity(self, stats: UsageStats):
        """Property: UsageStats survives JSON roundtrip without data loss."""
        json_str = stats.model_dump_json()
        recovered = UsageStats.model_validate_json(json_str)
        
        assert recovered.input_tokens == stats.input_tokens
        assert recovered.output_tokens == stats.output_tokens
        assert recovered.total_tokens == stats.total_tokens
        assert recovered.cache_read_input_tokens == stats.cache_read_input_tokens
        assert recovered.cache_creation_input_tokens == stats.cache_creation_input_tokens
        assert math.isclose(recovered.latency_ms, stats.latency_ms, rel_tol=1e-9)
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=500)
    def test_usage_stats_hash_is_stable(self, stats: UsageStats):
        """Property: hash is deterministic for identical data."""
        hash1 = hash(stats)
        hash2 = hash(stats)
        assert hash1 == hash2
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=500)
    def test_duplicate_stats_collapse_in_sets(self, stats: UsageStats):
        """Property: identical instances deduplicate in sets (hash equality)."""
        stats_set: Set[UsageStats] = {stats, stats, stats}
        assert len(stats_set) == 1
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=200)
    def test_usage_stats_cannot_be_mutated(self, stats: UsageStats):
        """Property: frozen instances reject all field mutation attempts."""
        with pytest.raises(ValidationError):
            stats.input_tokens = 999  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# BUDGET CONFIG PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestBudgetConfigProps:
    """Property-based tests for BudgetConfig logical consistency.
    
    Validates:
    - HARD_CAP strategy always has constraints
    - All limits are strictly positive
    - Unbounded detection accuracy
    - NaN/Infinity rejection
    - JSON serialization roundtrips
    - Enum deserialization
    - Immutability enforcement
    """
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_hard_cap_always_has_constraint(self, config: BudgetConfig):
        """Invariant: HARD_CAP strategy implies at least one limit is defined."""
        if config.strategy == BudgetStrategy.HARD_CAP:
            assert config.token_limit is not None or config.time_limit_ms is not None
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_all_limits_are_strictly_positive(self, config: BudgetConfig):
        """Constraint: all defined limits are strictly positive."""
        if config.token_limit is not None:
            assert config.token_limit > 0
        if config.time_limit_ms is not None:
            assert config.time_limit_ms > 0
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_unbounded_detection_is_accurate(self, config: BudgetConfig):
        """Property: is_unbounded correctly identifies absence of all constraints."""
        expected_unbounded = (config.token_limit is None and config.time_limit_ms is None)
        assert config.is_unbounded == expected_unbounded
    
    @given(token_limit=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=100)
    def test_nan_budget_time_limit_always_rejected(self, token_limit: int):
        """Property: NaN time limits are universally rejected."""
        with pytest.raises(ValidationError, match="cannot be NaN"):
            BudgetConfig(
                token_limit=token_limit,
                time_limit_ms=math.nan,
                strategy=BudgetStrategy.HARD_CAP
            )
    
    @given(token_limit=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=100)
    def test_infinity_budget_time_limit_always_rejected(self, token_limit: int):
        """Property: infinite time limits are universally rejected."""
        with pytest.raises(ValidationError, match="cannot be Infinity"):
            BudgetConfig(
                token_limit=token_limit,
                time_limit_ms=math.inf,
                strategy=BudgetStrategy.HARD_CAP
            )
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_budget_config_json_roundtrip_perfect_fidelity(self, config: BudgetConfig):
        """Property: BudgetConfig survives JSON roundtrip without data loss."""
        json_str = config.model_dump_json()
        recovered = BudgetConfig.model_validate_json(json_str)
        
        assert recovered.token_limit == config.token_limit
        if config.time_limit_ms is not None:
            assert math.isclose(recovered.time_limit_ms, config.time_limit_ms, rel_tol=1e-9)
        else:
            assert recovered.time_limit_ms is None
        assert recovered.strategy == config.strategy
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_enum_deserializes_to_proper_type(self, config: BudgetConfig):
        """Property: enum values deserialize as enum instances, not primitive strings."""
        json_str = config.model_dump_json()
        data = json.loads(json_str)
        
        # In JSON, strategy is a primitive value
        assert isinstance(data["strategy"], str)
        
        # After deserialization, it's an Enum
        recovered = BudgetConfig.model_validate_json(json_str)
        assert isinstance(recovered.strategy, BudgetStrategy)
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_budget_config_is_hashable(self, config: BudgetConfig):
        """Property: instances are hashable and usable as dict keys."""
        hash_value = hash(config)
        assert isinstance(hash_value, int)
    
    @given(config=valid_budget_config())
    @settings(max_examples=200)
    def test_budget_config_cannot_be_mutated(self, config: BudgetConfig):
        """Property: frozen instances reject all field mutation attempts."""
        with pytest.raises(ValidationError):
            config.token_limit = 12345  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION FUZZING
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegrationFuzzing:
    """High-level integration fuzzing across multiple components.
    
    Tests realistic workflows combining multiple validation steps.
    """
    
    @given(
        stats_list=st.lists(valid_usage_stats(), min_size=2, max_size=10)
    )
    @settings(max_examples=100)
    def test_massive_aggregation_maintains_invariants(self, stats_list: list[UsageStats]):
        """Property: batch aggregation preserves all algebraic and physical invariants."""
        # Aggregate all stats
        total = stats_list[0]
        for stats in stats_list[1:]:
            total = total + stats
        
        # Verify conservation law
        assert total.total_tokens == total.input_tokens + total.output_tokens
        
        # Verify cache coherence
        assert total.cache_read_input_tokens <= total.input_tokens
        
        # Verify non-negativity
        assert total.total_tokens >= 0
        assert total.latency_ms >= 0.0
        
        # Verify monotonicity (total >= any individual)
        for stats in stats_list:
            assert total.total_tokens >= stats.total_tokens
    
    @given(
        stats=valid_usage_stats(),
        config=valid_budget_config()
    )
    @settings(max_examples=200)
    def test_stats_and_config_serialize_independently(self, stats: UsageStats, config: BudgetConfig):
        """Property: stats and config roundtrip independently without interference."""
        # Serialize both
        stats_json = stats.model_dump_json()
        config_json = config.model_dump_json()
        
        # Deserialize both
        recovered_stats = UsageStats.model_validate_json(stats_json)
        recovered_config = BudgetConfig.model_validate_json(config_json)
        
        # Verify integrity
        assert recovered_stats.total_tokens == stats.total_tokens
        assert recovered_config.strategy == config.strategy