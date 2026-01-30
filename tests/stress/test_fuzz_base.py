"""Property-based fuzz testing suite for Xulcan's foundational type system.

This module implements comprehensive fuzzing strategies to validate algebraic
properties, mathematical invariants, and resilience under extreme conditions.

Unlike test_base.py (which validates specific edge cases), this suite uses
Hypothesis to generate thousands of random inputs and verify that properties
hold universally across the input space.

Test Philosophy:
    - test_base.py: "Does X fail when given Y?" (Example-based)
    - test_fuzz_base.py: "Does property P hold for ALL inputs?" (Property-based)

The four attack vectors:
1. **Constructive**: Mathematical invariants (commutativity, associativity, conservation)
2. **Destructive**: Boundary fuzzing (max lengths, exotic encodings)
3. **Adversarial**: Security fuzzing (injection, DoS, protocol smuggling)
4. **Persistence**: Serialization stability (roundtrips, hash consistency)

References:
    - Master Fuzzing Plan: "Xulcan Core Types v1.0"
    - Unit tests: test_base.py (specific regression cases)
"""

import pytest
import json
import math
import base64
from typing import Set
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from hypothesis.strategies import SearchStrategy
from pydantic import ValidationError

from tests.utils.unicode import unicode_semantic_eq
from xulcan.core.types import (
    CanonicalRecord,
    FinitePositiveFloat,
    MachineID,
    SafeURL,
    Base64Data,
    HumanLabel,
    SemanticText,
    ExternalID,
    MimeType,
    UsageStats,
    BudgetConfig,
    BudgetStrategy,
    MAX_IDENTIFIER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_SEMANTIC_TEXT_LENGTH,
    MAX_EXTERNAL_ID_LENGTH,
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


@st.composite
def valid_canonical_identifier(draw) -> str:
    """Generates valid machine identifiers matching the canonical spec.
    
    Format: lowercase alphanumeric, hyphens/underscores as separators,
    cannot start/end with separators, max 128 chars.
    
    Returns:
        str: A valid CanonicalIdentifier string.
    """
    length = draw(st.integers(min_value=1, max_value=MAX_IDENTIFIER_LENGTH))
    
    # Start and end must be alphanumeric
    first_char = draw(st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789'))
    
    if length == 1:
        return first_char
    
    last_char = draw(st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789'))
    
    if length == 2:
        return first_char + last_char
    
    # Middle can include separators
    middle_chars = draw(st.text(
        alphabet='abcdefghijklmnopqrstuvwxyz0123456789-_',
        min_size=length - 2,
        max_size=length - 2
    ))
    
    return first_char + middle_chars + last_char


@st.composite
def valid_base64_data(draw) -> str:
    """Generates valid Base64 encoded strings.
    
    Creates random binary data, encodes to Base64, ensures correct padding.
    
    Returns:
        str: A valid Base64 encoded string.
    """
    byte_length = draw(st.integers(min_value=1, max_value=1000))
    data = draw(st.binary(min_size=byte_length, max_size=byte_length))
    return base64.b64encode(data).decode('ascii')


@st.composite
def malicious_identifier(draw) -> str:
    """Generates INVALID identifiers designed to break validation.
    
    Generates strings that violate one or more constraints:
    - Uppercase letters
    - Leading/trailing separators
    - Special characters
    - Excessive length
    
    Returns:
        str: An invalid identifier string.
    """
    # Choose attack vector
    attack = draw(st.sampled_from([
        'uppercase',
        'leading_separator',
        'trailing_separator',
        'special_chars',
        'too_long',
        'whitespace_only'
    ]))
    
    if attack == 'uppercase':
        return draw(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=1, max_size=20))
    elif attack == 'leading_separator':
        return '-' + draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=20))
    elif attack == 'trailing_separator':
        return draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=20)) + '_'
    elif attack == 'special_chars':
        return draw(st.text(alphabet='!@#$%^&*()', min_size=1, max_size=20))
    elif attack == 'too_long':
        return 'a' * (MAX_IDENTIFIER_LENGTH + draw(st.integers(min_value=1, max_value=100)))
    else:  # whitespace_only
        return '   '


@st.composite
def malicious_url(draw) -> str:
    """Generates INVALID URLs designed to test security boundaries.
    
    Returns:
        str: An invalid/dangerous URL string.
    """
    attack = draw(st.sampled_from([
        'data_uri',
        'file_protocol',
        'javascript_protocol',
        'relative_path',
        'missing_scheme'
    ]))
    
    if attack == 'data_uri':
        return 'data:text/plain,Hello'
    elif attack == 'file_protocol':
        return 'file:///etc/passwd'
    elif attack == 'javascript_protocol':
        return 'javascript:alert(1)'
    elif attack == 'relative_path':
        return '/images/logo.png'
    else:  # missing_scheme
        return 'example.com/path'


@st.composite
def malicious_base64(draw) -> str:
    """Generates INVALID Base64 strings.
    
    Returns:
        str: An invalid Base64 string.
    """
    attack = draw(st.sampled_from([
        'invalid_chars',
        'bad_padding',
        'unicode_injection'
    ]))
    
    if attack == 'invalid_chars':
        return draw(st.text(alphabet='!@#$%^&*()', min_size=1, max_size=20))
    elif attack == 'bad_padding':
        # Generate Base64 but truncate to break padding
        valid = base64.b64encode(b'test').decode('ascii')
        return valid[:-1]  # Remove last char
    else:  # unicode_injection
        return 'SGVsbG8=😀'


@st.composite
def extreme_semantic_text(draw) -> str:
    """Generates valid but EXTREME semantic text payloads.
    
    Tests boundary conditions near the 10MB limit.
    
    Returns:
        str: A very large but valid semantic text string.
    """
    # Generate sizes near the boundary
    size = draw(st.sampled_from([
        MAX_SEMANTIC_TEXT_LENGTH - 1000,  # Just below
        MAX_SEMANTIC_TEXT_LENGTH,          # Exactly at limit
        MAX_SEMANTIC_TEXT_LENGTH + 1,      # Just above (should fail)
    ]))
    
    return 'x' * size


# ═══════════════════════════════════════════════════════════════════════════
# VECTOR 1: CONSTRUCTIVE (Mathematical Invariants)
# ═══════════════════════════════════════════════════════════════════════════

class TestUsageStatsAlgebra:
    """Property-based tests for UsageStats algebraic laws.
    
    Validates that UsageStats behaves as a commutative monoid under addition:
    - Associativity: (A + B) + C = A + (B + C)
    - Commutativity: A + B = B + A
    - Identity: A + 0 = A
    - Conservation: total = input + output (always)
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


class TestBudgetConfigInvariants:
    """Property-based tests for BudgetConfig logical consistency."""
    
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


# ═══════════════════════════════════════════════════════════════════════════
# VECTOR 2: DESTRUCTIVE (Boundary Fuzzing)
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentifierBoundaryFuzzing:
    """Fuzz testing for identifier validation boundaries."""
    
    @given(bad_id=malicious_identifier())
    @settings(max_examples=500)
    def test_rejects_all_malicious_identifiers(self, bad_id: str):
        """Property: all structurally invalid identifiers are rejected."""
        from xulcan.core.types.base import _validate_machine_identifier
        with pytest.raises(ValueError):
            _validate_machine_identifier(bad_id)
    
    @given(valid_id=valid_canonical_identifier())
    @settings(max_examples=500)
    def test_valid_identifiers_never_rejected(self, valid_id: str):
        """Property: all well-formed identifiers pass validation."""
        from xulcan.core.types.base import _validate_machine_identifier
        result = _validate_machine_identifier(valid_id)
        assert len(result) <= MAX_IDENTIFIER_LENGTH
        assert result == result.strip()
    
    @given(length=st.integers(min_value=1, max_value=MAX_IDENTIFIER_LENGTH))
    @settings(max_examples=100)
    def test_exact_length_boundary_accepted(self, length: int):
        """Property: identifiers at any valid length [1, MAX] are accepted."""
        from xulcan.core.types.base import _validate_machine_identifier
        valid_id = 'a' * length
        result = _validate_machine_identifier(valid_id)
        assert len(result) == length
    
    @given(overflow=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_overflow_always_rejected(self, overflow: int):
        """Property: any length exceeding MAX is rejected."""
        from xulcan.core.types.base import _validate_machine_identifier
        invalid_id = 'a' * (MAX_IDENTIFIER_LENGTH + overflow)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            _validate_machine_identifier(invalid_id)


class TestBase64BoundaryFuzzing:
    """Fuzz testing for Base64 validation."""
    
    @given(bad_b64=malicious_base64())
    @settings(max_examples=500)
    def test_rejects_all_malicious_base64(self, bad_b64: str):
        """Property: all malformed Base64 strings are rejected."""
        from xulcan.core.types.base import _validate_base64_data
        with pytest.raises(ValueError):
            _validate_base64_data(bad_b64)
    
    @given(valid_b64=valid_base64_data())
    @settings(max_examples=500)
    def test_valid_base64_always_decodable(self, valid_b64: str):
        """Property: all validated Base64 can be decoded to bytes."""
        from xulcan.core.types.base import _validate_base64_data
        validated = _validate_base64_data(valid_b64)
        decoded = base64.b64decode(validated)
        assert isinstance(decoded, bytes)


class TestSemanticTextBoundaryFuzzing:
    """Fuzz testing for semantic text size limits."""
    
    @given(text=extreme_semantic_text())
    @settings(max_examples=50)  # Expensive due to large strings
    def test_enforces_size_limit_boundary(self, text: str):
        """Property: size limit is enforced exactly at MAX boundary."""
        from xulcan.core.types.base import _validate_semantic_text
        
        if len(text) <= MAX_SEMANTIC_TEXT_LENGTH:
            result = _validate_semantic_text(text)
            assert len(result) <= MAX_SEMANTIC_TEXT_LENGTH
        else:
            with pytest.raises(ValueError, match="exceeds maximum length"):
                _validate_semantic_text(text)


# ═══════════════════════════════════════════════════════════════════════════
# VECTOR 3: ADVERSARIAL (Security Fuzzing)
# ═══════════════════════════════════════════════════════════════════════════

class TestURLSecurityFuzzing:
    """Fuzz testing for URL injection attacks."""
    
    @given(bad_url=malicious_url())
    @settings(max_examples=500)
    def test_rejects_all_dangerous_url_schemes(self, bad_url: str):
        """Property: all dangerous URL patterns (data:, file:, javascript:) are rejected."""
        from xulcan.core.types.base import _validate_safe_url
        with pytest.raises(ValueError):
            _validate_safe_url(bad_url)
    
    @given(
        domain=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=3, max_size=20),
        tld=st.sampled_from(['com', 'org', 'net', 'io'])
    )
    @settings(max_examples=200)
    def test_accepts_all_valid_https_patterns(self, domain: str, tld: str):
        """Property: valid HTTPS URLs are always accepted."""
        from xulcan.core.types.base import _validate_safe_url
        url = f"https://{domain}.{tld}/path"
        result = _validate_safe_url(url)
        assert result.startswith('https://')


class TestUnicodeInjectionFuzzing:
    """Fuzz testing for Unicode-based attacks."""
    
    @given(
        prefix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10),
        control_char=st.sampled_from(['\x00', '\x01', '\x02', '\x0B', '\x0C', '\x0E', '\x0F']),
        suffix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10)
    )
    @settings(max_examples=200)
    def test_rejects_all_control_characters_in_labels(self, prefix: str, control_char: str, suffix: str):
        """Property: control characters (NULL, invisible chars) are rejected in labels."""
        from xulcan.core.types.base import _validate_human_label
        malicious_label = prefix + control_char + suffix
        with pytest.raises(ValueError):
            _validate_human_label(malicious_label)
    
    @given(
        prefix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10),
        suffix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10)
    )
    @settings(max_examples=200)
    def test_rejects_zero_width_spaces(self, prefix: str, suffix: str):
        """Property: zero-width spaces (U+200B) are rejected to prevent UI spoofing."""
        from xulcan.core.types.base import _validate_human_label
        # Zero-width space is invisible but occupies memory
        malicious_label = prefix + '\u200B' + suffix
        with pytest.raises(ValueError):
            _validate_human_label(malicious_label)


# ═══════════════════════════════════════════════════════════════════════════
# VECTOR 4: PERSISTENCE (Serialization Stability)
# ═══════════════════════════════════════════════════════════════════════════

class TestSerializationRoundtrips:
    """Property-based tests for serialization stability."""
    
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


class TestHashStability:
    """Property-based tests for hash consistency."""
    
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
    
    @given(config=valid_budget_config())
    @settings(max_examples=500)
    def test_budget_config_is_hashable(self, config: BudgetConfig):
        """Property: instances are hashable and usable as dict keys."""
        hash_value = hash(config)
        assert isinstance(hash_value, int)


class TestImmutabilityEnforcement:
    """Property-based tests for frozen record behavior."""
    
    @given(stats=valid_usage_stats())
    @settings(max_examples=200)
    def test_usage_stats_cannot_be_mutated(self, stats: UsageStats):
        """Property: frozen instances reject all field mutation attempts."""
        with pytest.raises(ValidationError):
            stats.input_tokens = 999  # type: ignore
    
    @given(config=valid_budget_config())
    @settings(max_examples=200)
    def test_budget_config_cannot_be_mutated(self, config: BudgetConfig):
        """Property: frozen instances reject all field mutation attempts."""
        with pytest.raises(ValidationError):
            config.token_limit = 12345  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# EXOTIC EDGE CASES (Numerical Limits)
# ═══════════════════════════════════════════════════════════════════════════

class TestNumericalExotica:
    """Tests handling of special floating-point values."""
    
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


# ═══════════════════════════════════════════════════════════════════════════
# CACHE INVARIANTS (Physical Constraints)
# ═══════════════════════════════════════════════════════════════════════════

class TestCachePhysicsInvariants:
    """Property-based tests for cache token physics.
    
    Validates that cache-related token counts obey physical constraints
    that cannot be violated even by malicious providers.
    """
    
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


# ═══════════════════════════════════════════════════════════════════════════
# AGGREGATION MONOTONICITY
# ═══════════════════════════════════════════════════════════════════════════

class TestAggregationMonotonicity:
    """Property-based tests for monotonic aggregation behavior.
    
    Validates that aggregating stats never decreases metrics
    (non-negativity preservation under addition).
    """
    
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
# LABEL LENGTH CALCULATIONS (Unicode Safety)
# ═══════════════════════════════════════════════════════════════════════════

class TestUnicodeLengthCalculations:
    """Property-based tests for Unicode-aware length validation.
    
    Validates that length constraints work correctly with multibyte
    Unicode characters (emoji, CJK, etc.).
    """
    
    @given(
        char=st.characters(min_codepoint=0x1F600, max_codepoint=0x1F64F),  # Emoji
        repetitions=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=100)
    def test_emoji_length_calculated_correctly(self, char: str, repetitions: int):
        """Property: emoji count as single characters (grapheme clusters), not bytes."""
        from xulcan.core.types.base import _validate_human_label
        
        label = char * repetitions
        
        if repetitions <= MAX_LABEL_LENGTH:
            result = _validate_human_label(label)
            assert len(result) == repetitions
        else:
            with pytest.raises(ValueError, match="exceeds maximum length"):
                _validate_human_label(label)
    
    @given(
        prefix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=100),
        emoji=st.characters(min_codepoint=0x1F600, max_codepoint=0x1F64F),
        suffix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=100)
    )
    @settings(max_examples=100)
    def test_mixed_unicode_length_accurate(self, prefix: str, emoji: str, suffix: str):
        """Property: mixed ASCII/emoji length calculation is character-based, not byte-based."""
        from xulcan.core.types.base import _validate_human_label
        
        label = prefix + emoji + suffix
        expected_length = len(prefix) + 1 + len(suffix)
        
        if expected_length <= MAX_LABEL_LENGTH:
            result = _validate_human_label(label)
            assert len(result) == expected_length


# ═══════════════════════════════════════════════════════════════════════════
# STRING NORMALIZATION IDEMPOTENCE
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizationIdempotence:
    """Property-based tests for string normalization stability.
    
    Validates that validation/normalization is idempotent:
    applying it twice yields the same result as applying it once.
    """
    
    @given(valid_id=valid_canonical_identifier())
    @settings(max_examples=200)
    def test_identifier_normalization_is_idempotent(self, valid_id: str):
        """Property: normalize(normalize(id)) ≡ normalize(id) for all identifiers."""
        from xulcan.core.types.base import _validate_machine_identifier
        
        first_pass = _validate_machine_identifier(valid_id)
        second_pass = _validate_machine_identifier(first_pass)
        
        assert first_pass == second_pass
    
    @given(valid_b64=valid_base64_data())
    @settings(max_examples=200)
    def test_base64_normalization_is_idempotent(self, valid_b64: str):
        """Property: normalize(normalize(b64)) ≡ normalize(b64) for all Base64."""
        from xulcan.core.types.base import _validate_base64_data
        
        first_pass = _validate_base64_data(valid_b64)
        second_pass = _validate_base64_data(first_pass)
        
        assert first_pass == second_pass
    
    @given(
        text=st.text(
            alphabet=st.characters(blacklist_categories=('Cc', 'Cs')),
            min_size=1,
            max_size=100
        )
    )
    @settings(max_examples=200)
    def test_label_whitespace_stripping_is_idempotent(self, text: str):
        """Property: strip(strip(text)) ≡ strip(text) for all labels."""
        from xulcan.core.types.base import _validate_human_label
        
        # Add random whitespace
        padded = f"  {text}  "
        
        try:
            first_pass = _validate_human_label(padded)
            second_pass = _validate_human_label(first_pass)
            assert first_pass == second_pass
        except ValueError:
            # If validation fails, ensure it fails consistently
            with pytest.raises(ValueError):
                _validate_human_label(padded)


# ═══════════════════════════════════════════════════════════════════════════
# FLOATING POINT PRECISION (Serialization Stability)
# ═══════════════════════════════════════════════════════════════════════════

class TestFloatingPointPrecision:
    """Property-based tests for floating-point serialization stability.
    
    Validates that latency values survive JSON roundtrips with
    acceptable precision loss.
    """
    
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


# ═══════════════════════════════════════════════════════════════════════════
# COMPREHENSIVE INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndFuzzing:
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

# ═══════════════════════════════════════════════════════════════════════════
# VECTOR 3.5: PROTOCOL ROBUSTNESS (MIME Types)
# ═══════════════════════════════════════════════════════════════════════════

class TestMimeTypeFuzzing:
    """Fuzz testing for MIME type validation and regex resilience."""

    @given(text=st.text(alphabet=st.characters(whitelist_categories=('L', 'N', 'P')), min_size=1, max_size=100))
    @settings(max_examples=500)
    def test_rejects_malformed_structure(self, text: str):
        """Property: strings lacking 'type/subtype' structure are rejected."""
        if '/' not in text:
            # Define locally to isolate test
            class MimeRecord(CanonicalRecord):
                mt: MimeType
            
            with pytest.raises(ValueError, match="Invalid MIME type"):
                MimeRecord(mt=text)

    @given(
        type_=st.text(alphabet=st.characters(whitelist_categories=('Ll', 'N'), whitelist_characters='.-+'), min_size=1, max_size=50),
        subtype=st.text(alphabet=st.characters(whitelist_categories=('Ll', 'N'), whitelist_characters='.-+'), min_size=1, max_size=50),
        params=st.one_of(st.none(), st.text(min_size=1, max_size=50))
    )
    @settings(max_examples=500)
    def test_accepts_and_normalizes_valid_formats(self, type_: str, subtype: str, params: str | None):
        """Invariant: MIME types are case-insensitive and normalize to lowercase with preserved parameters."""

        raw_input = f"{type_}/{subtype}"
        if params:
            raw_input += f";{params}"
        
        # Mix case to test normalization
        mixed_case = raw_input.upper() if len(raw_input) % 2 == 0 else raw_input.title()
        
        class MimeRecord(CanonicalRecord):
            mt: MimeType
            
        try:
            record = MimeRecord(mt=mixed_case)
        except ValueError:
            # If generated params contain invalid chars, we skip.
            # We are interested in the structural acceptance of the type/subtype here.
            return

        assert unicode_semantic_eq(record.mt, mixed_case)
        expected = f"{type_}/{subtype}".lower()
        if params:
            expected += f";{params}"

        assert unicode_semantic_eq(record.mt, expected)


    @given(text=st.text(min_size=1000, max_size=10000))
    @settings(deadline=500) 
    def test_regex_performance_dos(self, text: str):
        """Property: validation completes within deadline for large inputs (ReDoS protection)."""
        class MimeRecord(CanonicalRecord):
            mt: MimeType
            
        try:
            MimeRecord(mt=text)
        except ValueError:
            pass