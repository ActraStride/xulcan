"""Comprehensive test suite for foundational primitives.

Tests cover architecture rules (immutability, schema strictness, frozen state),
semantic string validation (identifiers, labels), mathematical consistency 
(token accounting), and economic constraint logic (budgeting).
"""

import pytest
from pydantic import ValidationError
import warnings

from xulcan.core import (
    UsageStats,
    BudgetStrategy,
    BudgetConfig
)


# ═══════════════════════════════════════════════════════════════════════════
# USAGE STATS
# ═══════════════════════════════════════════════════════════════════════════

class TestMathematicalInvariants:
    """Token math consistency validation."""

    def test_accepts_valid_token_sum(self) -> None:
        """Should initialize correctly when input + output == total."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=500.0
        )
        assert stats.total_tokens == 150

    def test_rejects_inconsistent_token_sum(self) -> None:
        """Should raise ValueError if total_tokens != input + output."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=200,  # Wrong!
                latency_ms=500.0
            )
        
        assert "token math mismatch" in str(exc_info.value).lower()

    

    def test_rejects_cache_exceeds_input(self) -> None:
        """Should raise ValueError if cache_read_input_tokens > input_tokens."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                cache_read_input_tokens=150,  # Impossible!
                latency_ms=500.0
            )
        
        assert "cache read tokens" in str(exc_info.value).lower()

    def test_allows_full_cache_hit(self) -> None:
        """Should allow cache_read_input_tokens equal to input_tokens."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cache_read_input_tokens=100,
            latency_ms=500.0
        )
        assert stats.cache_read_input_tokens == stats.input_tokens


class TestTypeAndRangeValidation:
    """Type safety and boundary validation."""

    def test_rejects_negative_input_tokens(self) -> None:
        """Should raise ValidationError for negative input_tokens."""
        with pytest.raises(ValidationError):
            UsageStats(
                input_tokens=-10,
                output_tokens=50,
                total_tokens=40,
                latency_ms=500.0
            )

    def test_rejects_negative_output_tokens(self) -> None:
        """Should raise ValidationError for negative output_tokens."""
        with pytest.raises(ValidationError):
            UsageStats(
                input_tokens=100,
                output_tokens=-50,
                total_tokens=50,
                latency_ms=500.0
            )

    def test_rejects_negative_latency(self) -> None:
        """Should raise ValidationError for negative latency_ms."""
        with pytest.raises(ValidationError):
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=-100.0
            )

    def test_rejects_nan_latency(self) -> None:
        """Should raise ValidationError for NaN latency_ms."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=float('nan')
            )
        
        assert "nan" in str(exc_info.value).lower()

    def test_rejects_infinite_latency(self) -> None:
        """Should raise ValidationError for infinite latency_ms."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=float('inf')
            )
        
        assert "infinity" in str(exc_info.value).lower()


class TestPhysicalPlausibility:
    """Physical constraint validation (time/matter relationship)."""

    def test_warns_on_zero_latency_with_tokens(self) -> None:
        """Should emit UserWarning if tokens processed but latency is zero."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=0.0
            )
            
            assert len(w) == 1
            assert "physical inconsistency" in str(w[0].message).lower()

    def test_no_warning_on_full_cache_hit(self) -> None:
        """Should NOT emit warning for full cache hit with zero latency."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            UsageStats(
                input_tokens=100,
                output_tokens=0,
                total_tokens=100,
                cache_read_input_tokens=100,
                latency_ms=0
            )
            
            assert len(w) == 0

    def test_no_warning_on_empty_stats(self) -> None:
        """Should NOT emit warning if stats are completely empty."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            UsageStats.zero()
            
            assert len(w) == 0


class TestCalculatedProperties:
    """Computed property behavior."""

    def test_is_empty_for_zero_stats(self) -> None:
        """Should return True for is_empty only if tokens and latency are zero."""
        stats = UsageStats.zero()
        assert stats.is_empty is True

    def test_is_not_empty_with_tokens(self) -> None:
        """Should return False for is_empty if tokens exist."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=0.0
        )
        assert stats.is_empty is False

    def test_cache_efficiency_avoids_division_by_zero(self) -> None:
        """Should return 0.0 for cache_efficiency if input_tokens is zero."""
        stats = UsageStats.zero()
        assert stats.cache_efficiency == 0.0

    def test_cache_efficiency_calculation(self) -> None:
        """Should calculate cache_efficiency correctly."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cache_read_input_tokens=50,
            latency_ms=500.0
        )
        assert stats.cache_efficiency == 0.5

    def test_total_cache_tokens_sums_correctly(self) -> None:
        """Should sum cache_read and cache_creation tokens."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cache_read_input_tokens=30,
            cache_creation_input_tokens=20,
            latency_ms=500.0
        )
        assert stats.total_cache_tokens == 50


class TestArithmetic:
    """Object addition behavior."""

    def test_adds_two_usage_stats(self, valid_usage_stats: UsageStats) -> None:
        """Should correctly sum two UsageStats objects."""
        stats2 = UsageStats(
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
            cache_read_input_tokens=10,
            cache_creation_input_tokens=5,
            latency_ms=800.0
        )
        
        result = valid_usage_stats + stats2
        
        assert result.input_tokens == 150
        assert result.output_tokens == 75
        assert result.total_tokens == 225
        assert result.cache_read_input_tokens == 40
        assert result.cache_creation_input_tokens == 25
        assert result.latency_ms == 2000.0

    def test_rejects_addition_with_incompatible_type(self, valid_usage_stats: UsageStats) -> None:
        """Should raise TypeError when adding UsageStats with incompatible type."""
        with pytest.raises(TypeError):
            result = valid_usage_stats + 100  # type: ignore


class TestArithmeticEdgeCases:
    """Edge cases in usage arithmetic."""

    def test_adding_zero_is_identity(self) -> None:
        """Should maintain values when adding zero stats."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=1000.0
        )
        result = stats + UsageStats.zero()
        assert result == stats


class TestArithmeticIdentity:
    """Validation of arithmetic neutral elements."""

    def test_addition_with_zero_identity(self, valid_usage_stats: UsageStats) -> None:
        """Should return identical stats values when adding UsageStats.zero()."""
        zero = UsageStats.zero()
        result = valid_usage_stats + zero
        
        # Values must match
        assert result == valid_usage_stats
        
        # But object reference must be new (Immutability check)
        assert result is not valid_usage_stats


# ═══════════════════════════════════════════════════════════════════════════
# BUDGET CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class TestBusinessLogic:
    """Valid configuration scenarios."""

    def test_accepts_hard_cap_with_token_limit(self) -> None:
        """Should allow HARD_CAP if token_limit is defined."""
        budget = BudgetConfig(
            token_limit=1000,
            strategy=BudgetStrategy.HARD_CAP
        )
        assert budget.strategy == BudgetStrategy.HARD_CAP

    def test_accepts_hard_cap_with_time_limit(self) -> None:
        """Should allow HARD_CAP if time_limit_ms is defined."""
        budget = BudgetConfig(
            time_limit_ms=5000.0,
            strategy=BudgetStrategy.HARD_CAP
        )
        assert budget.strategy == BudgetStrategy.HARD_CAP

    def test_accepts_soft_notify_without_limits(self) -> None:
        """Should allow SOFT_NOTIFY without any limits defined."""
        budget = BudgetConfig(strategy=BudgetStrategy.SOFT_NOTIFY)
        assert budget.strategy == BudgetStrategy.SOFT_NOTIFY


class TestInvalidLogicalStates:
    """Configuration validation errors."""

    def test_rejects_hard_cap_without_limits(self) -> None:
        """Should raise ValueError if HARD_CAP but both limits are None."""
        with pytest.raises(ValidationError) as exc_info:
            BudgetConfig(strategy=BudgetStrategy.HARD_CAP)
        
        assert "unbounded hard cap" in str(exc_info.value).lower()

    def test_rejects_zero_token_limit(self) -> None:
        """Should raise ValidationError if token_limit is zero."""
        with pytest.raises(ValidationError):
            BudgetConfig(
                token_limit=0,
                strategy=BudgetStrategy.HARD_CAP
            )

    def test_rejects_negative_token_limit(self) -> None:
        """Should raise ValidationError if token_limit is negative."""
        with pytest.raises(ValidationError):
            BudgetConfig(
                token_limit=-100,
                strategy=BudgetStrategy.HARD_CAP
            )

    def test_rejects_zero_time_limit(self) -> None:
        """Should raise ValidationError if time_limit_ms is zero."""
        with pytest.raises(ValidationError):
            BudgetConfig(
                time_limit_ms=0.0,
                strategy=BudgetStrategy.HARD_CAP
            )

    def test_rejects_negative_time_limit(self) -> None:
        """Should raise ValidationError if time_limit_ms is negative."""
        with pytest.raises(ValidationError):
            BudgetConfig(
                time_limit_ms=-1000.0,
                strategy=BudgetStrategy.HARD_CAP
            )

    def test_rejects_nan_time_limit(self) -> None:
        """Should raise ValidationError if time_limit_ms is NaN."""
        with pytest.raises(ValidationError) as exc_info:
            BudgetConfig(
                time_limit_ms=float('nan'),
                strategy=BudgetStrategy.HARD_CAP
            )
        
        assert "nan" in str(exc_info.value).lower()

    def test_rejects_infinite_time_limit(self) -> None:
        """Should raise ValidationError if time_limit_ms is infinite."""
        with pytest.raises(ValidationError) as exc_info:
            BudgetConfig(
                time_limit_ms=float('inf'),
                strategy=BudgetStrategy.HARD_CAP
            )
        
        assert "infinity" in str(exc_info.value).lower()


class TestBoundednessDetection:
    """Unbounded configuration detection."""

    def test_is_unbounded_when_no_limits(self) -> None:
        """Should identify is_unbounded as True if both limits are None."""
        budget = BudgetConfig(strategy=BudgetStrategy.SOFT_NOTIFY)
        assert budget.is_unbounded is True

    def test_is_bounded_with_token_limit(self) -> None:
        """Should identify is_unbounded as False if token_limit is set."""
        budget = BudgetConfig(
            token_limit=1000,
            strategy=BudgetStrategy.HARD_CAP
        )
        assert budget.is_unbounded is False

    def test_is_bounded_with_time_limit(self) -> None:
        """Should identify is_unbounded as False if time_limit_ms is set."""
        budget = BudgetConfig(
            time_limit_ms=5000.0,
            strategy=BudgetStrategy.HARD_CAP
        )
        assert budget.is_unbounded is False


class TestEnumValues:
    """BudgetStrategy enumeration behavior."""

    def test_accepts_hard_cap_string(self) -> None:
        """Should accept 'hard_cap' string as valid strategy value."""
        budget = BudgetConfig(
            token_limit=1000,
            strategy="hard_cap"  # type: ignore
        )
        assert budget.strategy == "hard_cap"

    def test_accepts_soft_notify_string(self) -> None:
        """Should accept 'soft_notify' string as valid strategy value."""
        budget = BudgetConfig(strategy="soft_notify")  # type: ignore
        assert budget.strategy == "soft_notify"

    def test_rejects_invalid_strategy_string(self) -> None:
        """Should reject invalid strategy strings."""
        with pytest.raises(ValidationError):
            BudgetConfig(
                token_limit=1000,
                strategy="invalid_strategy"  # type: ignore
            )


# ═══════════════════════════════════════════════════════════════════════════
# SERIALIZATION AND ROUNDTRIP 
# ═══════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """Serialization roundtrip validation."""

    def test_usage_stats_json_roundtrip(self, valid_usage_stats: UsageStats) -> None:
        """Should survive JSON serialization -> deserialization cycle."""
        json_str = valid_usage_stats.model_dump_json()
        reconstructed = UsageStats.model_validate_json(json_str)
        
        assert reconstructed == valid_usage_stats

    def test_budget_config_dict_roundtrip(self, valid_budget: BudgetConfig) -> None:
        """Should survive dict serialization -> deserialization cycle."""
        data = valid_budget.model_dump()
        reconstructed = BudgetConfig.model_validate(data)

        assert reconstructed == valid_budget
        assert reconstructed.strategy == BudgetStrategy.HARD_CAP

    def test_model_dump_excludes_none_fields(self) -> None:
        """Should omit None fields from output when exclude_none=True is used (Wire-Format safety)."""
        # Config with one set limit and one unbounded (None) limit
        budget = BudgetConfig(
            token_limit=1000,
            time_limit_ms=None,
            strategy=BudgetStrategy.HARD_CAP
        )
        
        # Export for API transmission
        dumped = budget.model_dump(exclude_none=True)
        
        assert "token_limit" in dumped
        assert dumped["token_limit"] == 1000
        
        # Vital check: Key must be completely absent, not just null
        assert "time_limit_ms" not in dumped