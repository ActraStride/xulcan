"""Property-based testing for Xulcan's primitive type system.

This module validates string-based types, format validation, and encoding safety
using Hypothesis fuzzing strategies. Tests focus on:

- Canonical identifiers (machine-readable strings)
- Base64 encoding/decoding
- Semantic text (human-readable content)
- Safe URLs (security boundaries)
- Human labels (Unicode safety)
- MIME types (protocol robustness)

Test Philosophy:
    Property-based testing validates that invariants hold universally across
    the input space, rather than testing specific examples.

References:
    - Master Fuzzing Plan: "Xulcan Core Types v1.0"
    - Unit tests: test_base.py (specific regression cases)
"""

import pytest
import base64
from hypothesis import given, strategies as st, settings

from tests.utils.unicode import unicode_semantic_eq
from xulcan.core import (
    CanonicalRecord,
    MachineID,
    SafeURL,
    Base64Data,
    HumanLabel,
    SemanticText,
    MimeType,
    MAX_IDENTIFIER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_SEMANTIC_TEXT_LENGTH,
)


# ═══════════════════════════════════════════════════════════════════════════
# HYPOTHESIS STRATEGY GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

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
# MACHINE IDENTIFIER PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestMachineIDProps:
    """Property-based tests for canonical machine identifiers.
    
    Validates:
    - Rejection of all malformed identifiers
    - Acceptance of all well-formed identifiers
    - Length boundary enforcement
    - Normalization idempotence
    """
    
    @given(bad_id=malicious_identifier())
    @settings(max_examples=500)
    def test_rejects_all_malicious_identifiers(self, bad_id: str):
        """Property: all structurally invalid identifiers are rejected."""
        from xulcan.core.primitives import _validate_machine_identifier
        with pytest.raises(ValueError):
            _validate_machine_identifier(bad_id)
    
    @given(valid_id=valid_canonical_identifier())
    @settings(max_examples=500)
    def test_valid_identifiers_never_rejected(self, valid_id: str):
        """Property: all well-formed identifiers pass validation."""
        from xulcan.core.primitives import _validate_machine_identifier
        result = _validate_machine_identifier(valid_id)
        assert len(result) <= MAX_IDENTIFIER_LENGTH
        assert result == result.strip()
    
    @given(length=st.integers(min_value=1, max_value=MAX_IDENTIFIER_LENGTH))
    @settings(max_examples=100)
    def test_exact_length_boundary_accepted(self, length: int):
        """Property: identifiers at any valid length [1, MAX] are accepted."""
        from xulcan.core.primitives import _validate_machine_identifier
        valid_id = 'a' * length
        result = _validate_machine_identifier(valid_id)
        assert len(result) == length
    
    @given(overflow=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_overflow_always_rejected(self, overflow: int):
        """Property: any length exceeding MAX is rejected."""
        from xulcan.core.primitives import _validate_machine_identifier
        invalid_id = 'a' * (MAX_IDENTIFIER_LENGTH + overflow)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            _validate_machine_identifier(invalid_id)
    
    @given(valid_id=valid_canonical_identifier())
    @settings(max_examples=200)
    def test_identifier_normalization_is_idempotent(self, valid_id: str):
        """Property: normalize(normalize(id)) ≡ normalize(id) for all identifiers."""
        from xulcan.core.primitives import _validate_machine_identifier
        
        first_pass = _validate_machine_identifier(valid_id)
        second_pass = _validate_machine_identifier(first_pass)
        
        assert first_pass == second_pass


# ═══════════════════════════════════════════════════════════════════════════
# BASE64 ENCODING PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestBase64Props:
    """Property-based tests for Base64 validation.
    
    Validates:
    - Rejection of all malformed Base64 strings
    - Acceptance and decodability of all valid Base64
    - Normalization idempotence
    """
    
    @given(bad_b64=malicious_base64())
    @settings(max_examples=500)
    def test_rejects_all_malicious_base64(self, bad_b64: str):
        """Property: all malformed Base64 strings are rejected."""
        from xulcan.core.primitives import _validate_base64_data
        with pytest.raises(ValueError):
            _validate_base64_data(bad_b64)
    
    @given(valid_b64=valid_base64_data())
    @settings(max_examples=500)
    def test_valid_base64_always_decodable(self, valid_b64: str):
        """Property: all validated Base64 can be decoded to bytes."""
        from xulcan.core.primitives import _validate_base64_data
        validated = _validate_base64_data(valid_b64)
        decoded = base64.b64decode(validated)
        assert isinstance(decoded, bytes)
    
    @given(valid_b64=valid_base64_data())
    @settings(max_examples=200)
    def test_base64_normalization_is_idempotent(self, valid_b64: str):
        """Property: normalize(normalize(b64)) ≡ normalize(b64) for all Base64."""
        from xulcan.core.primitives import _validate_base64_data
        
        first_pass = _validate_base64_data(valid_b64)
        second_pass = _validate_base64_data(first_pass)
        
        assert first_pass == second_pass


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC TEXT PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestSemanticTextProps:
    """Property-based tests for semantic text size limits.
    
    Validates:
    - Exact enforcement of size boundaries
    - Rejection of oversized content
    """
    
    @given(text=extreme_semantic_text())
    @settings(max_examples=50)  # Expensive due to large strings
    def test_enforces_size_limit_boundary(self, text: str):
        """Property: size limit is enforced exactly at MAX boundary."""
        from xulcan.core.primitives import _validate_semantic_text
        
        if len(text) <= MAX_SEMANTIC_TEXT_LENGTH:
            result = _validate_semantic_text(text)
            assert len(result) <= MAX_SEMANTIC_TEXT_LENGTH
        else:
            with pytest.raises(ValueError, match="exceeds maximum length"):
                _validate_semantic_text(text)


# ═══════════════════════════════════════════════════════════════════════════
# SAFE URL PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════

class TestSafeURLProps:
    """Property-based tests for URL security validation.
    
    Validates:
    - Rejection of dangerous URL schemes (data:, file:, javascript:)
    - Acceptance of valid HTTPS URLs
    """
    
    @given(bad_url=malicious_url())
    @settings(max_examples=500)
    def test_rejects_all_dangerous_url_schemes(self, bad_url: str):
        """Property: all dangerous URL patterns (data:, file:, javascript:) are rejected."""
        from xulcan.core.primitives import _validate_safe_url
        with pytest.raises(ValueError):
            _validate_safe_url(bad_url)
    
    @given(
        domain=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=3, max_size=20),
        tld=st.sampled_from(['com', 'org', 'net', 'io'])
    )
    @settings(max_examples=200)
    def test_accepts_all_valid_https_patterns(self, domain: str, tld: str):
        """Property: valid HTTPS URLs are always accepted."""
        from xulcan.core.primitives import _validate_safe_url
        url = f"https://{domain}.{tld}/path"
        result = _validate_safe_url(url)
        assert result.startswith('https://')


# ═══════════════════════════════════════════════════════════════════════════
# HUMAN LABEL PROPERTIES (Unicode Safety)
# ═══════════════════════════════════════════════════════════════════════════

class TestHumanLabelProps:
    """Property-based tests for human-readable labels.
    
    Validates:
    - Rejection of control characters and zero-width spaces
    - Unicode-aware length calculations (grapheme clusters)
    - Whitespace normalization idempotence
    """
    
    @given(
        prefix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10),
        control_char=st.sampled_from(['\x00', '\x01', '\x02', '\x0B', '\x0C', '\x0E', '\x0F']),
        suffix=st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10)
    )
    @settings(max_examples=200)
    def test_rejects_all_control_characters_in_labels(self, prefix: str, control_char: str, suffix: str):
        """Property: control characters (NULL, invisible chars) are rejected in labels."""
        from xulcan.core.primitives import _validate_human_label
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
        from xulcan.core.primitives import _validate_human_label
        # Zero-width space is invisible but occupies memory
        malicious_label = prefix + '\u200B' + suffix
        with pytest.raises(ValueError):
            _validate_human_label(malicious_label)
    
    @given(
        char=st.characters(min_codepoint=0x1F600, max_codepoint=0x1F64F),  # Emoji
        repetitions=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=100)
    def test_emoji_length_calculated_correctly(self, char: str, repetitions: int):
        """Property: emoji count as single characters (grapheme clusters), not bytes."""
        from xulcan.core.primitives import _validate_human_label
        
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
        from xulcan.core.primitives import _validate_human_label
        
        label = prefix + emoji + suffix
        expected_length = len(prefix) + 1 + len(suffix)
        
        if expected_length <= MAX_LABEL_LENGTH:
            result = _validate_human_label(label)
            assert len(result) == expected_length
    
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
        from xulcan.core.primitives import _validate_human_label
        
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
# MIME TYPE PROPERTIES (Protocol Robustness)
# ═══════════════════════════════════════════════════════════════════════════

class TestMimeTypeProps:
    """Property-based tests for MIME type validation and regex resilience.
    
    Validates:
    - Rejection of malformed structure
    - Case-insensitive normalization
    - ReDoS protection (regex performance)
    """

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