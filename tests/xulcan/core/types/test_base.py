"""Comprehensive test suite for foundational primitives.

Tests cover architecture rules (immutability, schema strictness, frozen state),
semantic string validation (identifiers, labels), mathematical consistency 
(token accounting), and economic constraint logic (budgeting).
"""

from typing import Optional
import pytest
from pydantic import ValidationError
from enum import Enum
import warnings

from xulcan.core.types import (
    CanonicalRecord,
    FinitePositiveFloat,
    MachineID,
    SafeURL,
    Base64Data,
    ExternalID,
    MimeType,
    HumanLabel,
    SemanticText,
    UsageStats,
    BudgetStrategy,
    BudgetConfig,
    MAX_IDENTIFIER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_SEMANTIC_TEXT_LENGTH
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def dummy_record_class() -> type[CanonicalRecord]:
    """Provides a concrete implementation of CanonicalRecord for testing."""
    class DummyRecord(CanonicalRecord):
        name: str
        value: int = 0
    return DummyRecord


@pytest.fixture
def dummy_enum() -> type[Enum]:
    """Provides a test enum for serialization validation."""
    class TestStatus(str, Enum):
        ACTIVE = "active"
        INACTIVE = "inactive"
    return TestStatus


@pytest.fixture
def valid_usage_stats() -> UsageStats:
    """Provides a valid UsageStats instance."""
    return UsageStats(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
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


# ═══════════════════════════════════════════════════════════════════════════
# CANONICAL RECORD BASE CLASS
# ═══════════════════════════════════════════════════════════════════════════

class TestImmutability:
    """Frozen state validation."""

    def test_cannot_modify_attribute(self, dummy_record_class) -> None:
        """Should raise error when attempting to reassign an attribute."""
        record = dummy_record_class(name="test", value=42)
        with pytest.raises(ValidationError):
            record.name = "changed"  # type: ignore

    def test_cannot_delete_attribute(self, dummy_record_class) -> None:
        """Should raise error when attempting to delete an attribute."""
        record = dummy_record_class(name="test")
        with pytest.raises((ValidationError, AttributeError)):
            del record.name  # type: ignore

    def test_is_hashable(self, dummy_record_class) -> None:
        """Should allow instances to be used as dictionary keys."""
        record = dummy_record_class(name="test")
        test_dict = {record: "value"}
        assert test_dict[record] == "value"

    def test_identical_instances_have_same_hash(self, dummy_record_class) -> None:
        """Should maintain the same hash for distinct instances with identical data."""
        record1 = dummy_record_class(name="test", value=42)
        record2 = dummy_record_class(name="test", value=42)
        assert hash(record1) == hash(record2)


class TestSchemaStrictness:
    """Schema strictness (extra='forbid')."""

    def test_rejects_unknown_fields(self, dummy_record_class) -> None:
        """Should raise ValidationError if unknown fields are provided."""
        with pytest.raises(ValidationError) as exc_info:
            dummy_record_class(name="test", unknown_field=123)
        
        errors = exc_info.value.errors()
        assert any(e['type'] == 'extra_forbidden' for e in errors)

    def test_accepts_valid_fields_only(self, dummy_record_class) -> None:
        """Should accept instances with only defined fields."""
        record = dummy_record_class(name="test", value=42)
        assert record.name == "test"
        assert record.value == 42


class TestEnumSerialization:
    """Enum handling (NO use_enum_values)."""

    def test_serializes_enum_conditionally(self, dummy_record_class, dummy_enum) -> None:
        """Should preserve Enum objects in Python dumps but serialize to primitives for JSON."""
        class RecordWithEnum(CanonicalRecord):
            status: dummy_enum
        
        record = RecordWithEnum(status=dummy_enum.ACTIVE)
        
        # Standard Python dump: Should keep the Enum object (rich type validation)
        dumped_py = record.model_dump()
        assert dumped_py['status'] == dummy_enum.ACTIVE
        assert isinstance(dumped_py['status'], dummy_enum)
        
        # JSON dump: Should flatten to primitive string (interoperability)
        dumped_json = record.model_dump(mode="json")
        assert dumped_json['status'] == dummy_enum.ACTIVE.value
        assert isinstance(dumped_json['status'], str)

    def test_accepts_primitive_enum_values(self, dummy_record_class, dummy_enum) -> None:
        """Should accept primitive values that correspond to Enum members."""
        class RecordWithEnum(CanonicalRecord):
            status: dummy_enum
        
        record = RecordWithEnum(status="active")
        assert record.status == dummy_enum.ACTIVE

    def test_rejects_invalid_enum_values(self, dummy_record_class, dummy_enum) -> None:
        """Should raise ValidationError for invalid Enum primitive values."""
        class RecordWithEnum(CanonicalRecord):
            status: dummy_enum
        
        with pytest.raises(ValidationError):
            RecordWithEnum(status="invalid_status")


# ═══════════════════════════════════════════════════════════════════════════
# FINITE POSITIVE FLOAT TYPE
# ═══════════════════════════════════════════════════════════════════════════


class TestFinitePositiveFloat:
    """Finite positive float validation (used for latency/time)."""

    def test_accepts_simple_positive_float(self) -> None:
        """Should accept a standard positive floating point number."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None
        
        record = TestRecord(val=123.456)
        assert record.val == 123.456

    def test_accepts_zero(self) -> None:
        """Should accept 0.0 as a valid non-negative number."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        record = TestRecord(val=0.0)
        assert record.val == 0.0

    def test_accepts_none(self) -> None:
        """Should pass None through without validation errors (Optional support)."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        record = TestRecord(val=None)
        assert record.val is None

    def test_accepts_scientific_notation(self) -> None:
        """Should handle scientific notation correctly."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        record = TestRecord(val=1e-5)
        assert record.val == 0.00001

    def test_rejects_negative_value(self) -> None:
        """Should raise ValidationError for negative numbers (even tiny ones)."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(val=-0.0000001)
        
        assert "cannot be negative" in str(exc_info.value).lower()

    def test_rejects_nan(self) -> None:
        """Should explicitly reject Not-a-Number (NaN) values."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(val=float('nan'))
        
        assert "cannot be nan" in str(exc_info.value).lower()

    def test_rejects_positive_infinity(self) -> None:
        """Should reject positive infinity."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(val=float('inf'))
        
        assert "cannot be infinity" in str(exc_info.value).lower()

    def test_rejects_negative_infinity(self) -> None:
        """Should reject negative infinity."""
        class TestRecord(CanonicalRecord):
            val: Optional[FinitePositiveFloat] = None

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(val=float('-inf'))
        
        # Note: Depending on impl, might hit 'infinity' check before 'negative' check
        assert "cannot be infinity" in str(exc_info.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC STRING TYPES
# ═══════════════════════════════════════════════════════════════════════════

class TestMachineID:
    """Machine identifier validation."""

    def test_strips_whitespace(self) -> None:
        """Should automatically strip leading and trailing whitespace."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        record = TestRecord(id="  test_id  ")
        assert record.id == "test_id"

    def test_rejects_whitespace_only(self) -> None:
        """Should treat whitespace-only strings as empty and raise error."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id="   ")
        
        assert "cannot be empty or whitespace only" in str(exc_info.value).lower()

    def test_rejects_invalid_chars(self) -> None:
        """Should raise ValueError for strings with invalid characters."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id="Test-Id")
        assert "invalid identifier" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id="test id")
        assert "invalid identifier" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id="test@id")
        assert "invalid identifier" in str(exc_info.value).lower()


    def test_accepts_valid_alphanumeric(self) -> None:
        """Should accept standard alphanumeric strings without changes."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        record = TestRecord(id="valid_id_123")
        assert record.id == "valid_id_123"

    def test_rejects_none(self) -> None:
        """Should raise ValidationError if the string is None."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        with pytest.raises(ValidationError):
            TestRecord(id=None)

    def test_rejects_empty_string(self) -> None:
        """Should raise ValidationError if the string is empty."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id="")
        
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_accepts_max_length(self) -> None:
        """Should accept a string of exactly 128 characters."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        max_id = "x" * MAX_IDENTIFIER_LENGTH
        record = TestRecord(id=max_id)
        assert len(record.id) == MAX_IDENTIFIER_LENGTH

    def test_rejects_exceeds_max_length(self) -> None:
        """Should raise ValueError for a string of 129 characters."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        too_long = "x" * (MAX_IDENTIFIER_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(id=too_long)
        
        assert "exceeds maximum length" in str(exc_info.value).lower()

    def test_rejects_non_string_types(self) -> None:
        """Should raise ValidationError for non-string types like int or float."""
        class TestRecord(CanonicalRecord):
            id: MachineID
        
        with pytest.raises(ValidationError):
            TestRecord(id=12345)  # type: ignore


class TestSafeURL:
    """Security and format validation for absolute HTTP/HTTPS URLs."""

    def test_accepts_valid_https(self) -> None:
        """Should accept standard URLs with domain and TLD."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        record = TestRecord(url="https://api.openai.com/v1")
        assert record.url == "https://api.openai.com/v1"

    def test_accepts_http_localhost(self) -> None:
        """Should accept localhost and explicit IPs (needed for internal/dev networks)."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        record_localhost = TestRecord(url="http://localhost:8000")
        assert record_localhost.url == "http://localhost:8000"
        
        record_ip = TestRecord(url="http://192.168.1.1:3000")
        assert record_ip.url == "http://192.168.1.1:3000"

    def test_accepts_url_with_query_params(self) -> None:
        """Should allow complex URLs with parameters."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        record = TestRecord(url="https://site.com?q=hello&ref=1")
        assert record.url == "https://site.com?q=hello&ref=1"

    def test_rejects_missing_scheme(self) -> None:
        """Should raise ValidationError if protocol is missing."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="google.com")
        assert "invalid url format" in str(exc_info.value).lower()
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="//api.com")
        assert "relative" in str(exc_info.value).lower()

    def test_rejects_non_web_schemes(self) -> None:
        """Should reject dangerous schemes like file://, ftp://, or javascript:."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="file:///etc/passwd")
        assert "invalid url format" in str(exc_info.value).lower()
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="ftp://files.example.com")
        assert "invalid url format" in str(exc_info.value).lower()
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="javascript:alert(1)")
        assert "invalid url format" in str(exc_info.value).lower()

    def test_rejects_relative_paths(self) -> None:
        """Should reject non-absolute paths as they are not canonical."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="/api/v1/chat")
        assert "relative urls are not allowed" in str(exc_info.value).lower()

    def test_rejects_data_uris(self) -> None:
        """Should reject data: URIs to prevent large payloads or XSS injection."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="data:text/plain;base64,SGVsbG8gV29ybGQ=")
        assert "data uris are not allowed" in str(exc_info.value).lower()

    def test_rejects_whitespace_injection(self) -> None:
        """Should fail if URL contains spaces or unescaped control characters."""
        class TestRecord(CanonicalRecord):
            url: SafeURL
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(url="https://example.com/path with spaces")
        assert "invalid url format" in str(exc_info.value).lower()


class TestBase64Data:
    """Binary data integrity validation."""

    def test_accepts_valid_rfc4648_string(self) -> None:
        """Should accept a valid Base64 string (RFC 4648)."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        # "Hello World" encoded
        record = TestRecord(data="SGVsbG8gV29ybGQ=")
        assert record.data == "SGVsbG8gV29ybGQ="

    def test_strips_whitespace_automatically(self) -> None:
        """Should clean newlines, carriage returns, or spaces before validation."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        # Common in PEM headers or dirty API responses
        record = TestRecord(data="  SGVs\nbG8g\rV29y\nbGQ=  ")
        assert record.data == "SGVsbG8gV29ybGQ="
        assert "\n" not in record.data
        assert " " not in record.data

    def test_rejects_invalid_padding(self) -> None:
        """Should raise ValidationError if length is not multiple of 4 (missing padding)."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="SGVsbG8gV29ybGQ")  # Missing '='
        assert "corrupt base64" in str(exc_info.value).lower()

    def test_rejects_non_base64_alphabet(self) -> None:
        """Should reject characters not in Base64 alphabet."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="SGVsbG8*V29ybGQ=")  # Invalid '*'
        assert "invalid base64 characters" in str(exc_info.value).lower()
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="Hello?World!")  # Invalid '?' and '!'
        assert "invalid base64 characters" in str(exc_info.value).lower()
    
    def test_rejects_unicode_characters(self) -> None:
        """Should raise ValidationError when non-ASCII Unicode characters (emojis/kanji) are present."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        # Attempt to inject a poop emoji (💩) into the payload
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="SGVsbG8g8J+SlA==V29ybGQ=")
        
        assert "invalid base64 characters" in str(exc_info.value).lower()

    def test_rejects_url_safe_chars_if_strict(self) -> None:
        """Should reject URL-safe Base64 chars (-_) if enforcing standard (+/)."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        # URL-safe Base64 uses '-' and '_' instead of '+' and '/'
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="SGVsbG8-V29ybGQ_")
        assert "invalid base64 characters" in str(exc_info.value).lower()

    def test_handles_empty_string(self) -> None:
        """Should raise ValidationError for empty string (no valid data)."""
        class TestRecord(CanonicalRecord):
            data: Base64Data
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(data="")
        assert "cannot be empty" in str(exc_info.value).lower()


class TestHumanLabel:
    """Human-readable label validation."""

    def test_rejects_newline(self) -> None:
        """Should raise ValueError if contains newline character."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label="line1\nline2")
        
        assert "single line" in str(exc_info.value).lower()

    def test_rejects_carriage_return(self) -> None:
        """Should raise ValueError if contains carriage return."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label="text\rmore")
        
        assert "single line" in str(exc_info.value).lower()

    def test_rejects_tab_character(self) -> None:
        """Should raise ValueError if contains tab character."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label="text\ttab")
        
        assert "non-printable" in str(exc_info.value).lower()

    def test_rejects_null_character(self) -> None:
        """Should raise ValueError if contains null character."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label="text\0null")
        
        assert "non-printable" in str(exc_info.value).lower()

    def test_rejects_invisible_control_chars(self) -> None:
        """Should raise ValueError if contains invisible control characters."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label="text\x07bell")  # Bell character
        
        assert "non-printable" in str(exc_info.value).lower()

    def test_accepts_unicode_printable(self) -> None:
        """Should allow printable Unicode characters."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        record = TestRecord(label="Hello 世界 🌍 Café")
        assert record.label == "Hello 世界 🌍 Café"

    def test_accepts_max_length(self) -> None:
        """Should accept a string of exactly 256 characters."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        max_label = "x" * MAX_LABEL_LENGTH
        record = TestRecord(label=max_label)
        assert len(record.label) == MAX_LABEL_LENGTH

    def test_rejects_exceeds_max_length(self) -> None:
        """Should raise ValueError for a string of 257 characters."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        too_long = "x" * (MAX_LABEL_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(label=too_long)
        
        assert "exceeds maximum length" in str(exc_info.value).lower()

    def test_calculates_length_correctly_for_multibyte(self) -> None:
        """Should calculate length correctly for multibyte Unicode characters."""
        class TestRecord(CanonicalRecord):
            label: HumanLabel
        
        # Each emoji is one character in Python's len(), regardless of bytes
        emoji_label = "🌍" * MAX_LABEL_LENGTH
        record = TestRecord(label=emoji_label)
        assert len(record.label) == MAX_LABEL_LENGTH


class TestHumanLabelInheritance:
    """Validation of inherited behaviors in HumanLabel."""

    def test_strips_whitespace_implicitly(self) -> None:
        """Should automatically strip whitespace due to inherited identifier logic."""
        class LabelRecord(CanonicalRecord):
            label: HumanLabel
            
        # The user types "  My Label  " in the UI
        record = LabelRecord(label="  User Interface  ")
        
        # The system stores "User Interface"
        assert record.label == "User Interface"
        assert len(record.label) == 14  # Not 18


class TestSemanticText:
    """Validation for raw semantic content (prompts, code)."""

    def test_preserves_whitespace_fidelity(self) -> None:
        """Should NOT strip leading/trailing whitespace (crucial for code indentation)."""
        class TextRecord(CanonicalRecord):
            content: SemanticText
        
        # Python code block with indentation
        raw_text = "    def foo():\n        return True\n"
        record = TextRecord(content=raw_text)
        
        # Must be byte-for-byte identical
        assert record.content == raw_text
        assert record.content.startswith("    ")
        assert record.content.endswith("\n")

    def test_accepts_empty_string(self) -> None:
        """Should accept empty strings (unlike Identifiers)."""
        class TextRecord(CanonicalRecord):
            content: SemanticText
            
        record = TextRecord(content="")
        assert record.content == ""

    def test_accepts_max_length(self) -> None:
        """Should accept a string of exactly 10,000,000 characters."""
        class TextRecord(CanonicalRecord):
            content: SemanticText
        
        max_content = "a" * MAX_SEMANTIC_TEXT_LENGTH
        record = TextRecord(content=max_content)
        assert len(record.content) == MAX_SEMANTIC_TEXT_LENGTH

    def test_rejects_exceeds_max_length(self) -> None:
        """Should raise ValidationError for a string exceeding 10,000,000 characters."""
        class TextRecord(CanonicalRecord):
            content: SemanticText
        
        too_long = "a" * (MAX_SEMANTIC_TEXT_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            TextRecord(content=too_long)
        
        assert "exceeds maximum length" in str(exc_info.value).lower()


class TestExternalID:
    """External provider ID validation."""
    
    def test_accepts_openai_message_id(self) -> None:
        """Should accept OpenAI's msg_xxx format."""
        class TestRecord(CanonicalRecord):
            ext_id: ExternalID
        
        record = TestRecord(ext_id="msg_abc123XYZ")
        assert record.ext_id == "msg_abc123XYZ"
    
    def test_accepts_anthropic_message_id(self) -> None:
        """Should accept Anthropic's msg_xxx format."""
        class TestRecord(CanonicalRecord):
            ext_id: ExternalID
        
        record = TestRecord(ext_id="msg_01234567890abcdef")
        assert record.ext_id == "msg_01234567890abcdef"
    
    def test_accepts_spaces_and_dashes(self) -> None:
        """Should accept provider IDs with spaces/special chars."""
        class TestRecord(CanonicalRecord):
            ext_id: ExternalID
        
        # Some providers use UUIDs with dashes
        record = TestRecord(ext_id="550e8400-e29b-41d4-a716-446655440000")
        assert record.ext_id == "550e8400-e29b-41d4-a716-446655440000"
    
    def test_rejects_control_characters(self) -> None:
        """Should reject NULL bytes and invisible chars."""
        class TestRecord(CanonicalRecord):
            ext_id: ExternalID
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(ext_id="msg_\x00evil")
        assert "unsafe control characters" in str(exc_info.value).lower()


class TestMimeType:
    """Standard MIME type validation."""
    
    def test_accepts_standard_types(self) -> None:
        """Should accept common MIME types."""
        class TestRecord(CanonicalRecord):
            mime: MimeType
        
        valid_types = [
            "image/png",
            "application/json",
            "text/plain",
            "audio/mpeg",
            "video/mp4"
        ]
        
        for mime in valid_types:
            record = TestRecord(mime=mime)
            assert record.mime == mime.lower()  # Normalized to lowercase
    
    def test_normalizes_case(self) -> None:
        """Should convert to lowercase (MIME types are case-insensitive)."""
        class TestRecord(CanonicalRecord):
            mime: MimeType
        
        record = TestRecord(mime="IMAGE/PNG")
        assert record.mime == "image/png"
    
    def test_accepts_parameters(self) -> None:
        """Should accept MIME types with parameters."""
        class TestRecord(CanonicalRecord):
            mime: MimeType
        
        record = TestRecord(mime="text/plain;charset=utf-8")
        assert record.mime == "text/plain;charset=utf-8"
    
    def test_rejects_invalid_format(self) -> None:
        """Should reject strings without type/subtype structure."""
        class TestRecord(CanonicalRecord):
            mime: MimeType
        
        with pytest.raises(ValidationError) as exc_info:
            TestRecord(mime="notamimetype")
        assert "invalid mime type format" in str(exc_info.value).lower()

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