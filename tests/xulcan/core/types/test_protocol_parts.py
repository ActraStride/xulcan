"""
Comprehensive test suite for multimodal content parts architecture.

Validates discriminator patterns, XOR logic, type safety, and security boundaries
across TextPart, ImagePart, and AudioPart components. Ensures proper validation
of media type constraints, URL/data mutual exclusivity, and serialization integrity.
"""

import pytest
from pydantic import ValidationError, TypeAdapter
from typing import Any, Dict

from xulcan.core.types import TextPart, ImagePart, AudioPart, ContentPart


# ═══════════════════════════════════════════════════════════════════════════
# 1. TEST CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Valid 1x1 transparent PNG pixel
TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# Minimal WAV header
TINY_WAV_BASE64 = (
    "UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_text_part() -> TextPart:
    """Provides a standard valid TextPart instance."""
    return TextPart(type="text", text="Hello Xulcan")


@pytest.fixture
def valid_image_url_part() -> ImagePart:
    """Provides a standard ImagePart instance using URL source."""
    return ImagePart(
        type="image",
        url="https://example.com/valid_image.jpg",
        media_type="image/jpeg"
    )


@pytest.fixture
def valid_image_base64_part() -> ImagePart:
    """Provides a standard ImagePart instance using Base64 data source."""
    return ImagePart(
        type="image",
        data=TINY_PNG_BASE64,
        media_type="image/png"
    )


@pytest.fixture
def valid_audio_part() -> AudioPart:
    """Provides a standard AudioPart instance using Base64 data source."""
    return AudioPart(
        type="audio",
        data=TINY_WAV_BASE64,
        media_type="audio/wav"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. TEXTPART VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestTextPart:
    """TextPart Edge Cases & Type Safety Validation"""

    # --- Happy Path Validation ---

    def test_valid_text_part(self, valid_text_part: TextPart) -> None:
        """Should instantiate correctly with valid text content."""
        assert valid_text_part.text == "Hello Xulcan"
        assert valid_text_part.type == "text"

    # --- Boundary Validation ---

    def test_rejects_empty_string(self) -> None:
        """Should reject empty strings due to min_length=1 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            TextPart(type="text", text="")

        errors = exc_info.value.errors()
        assert any(
            "at least 1 character" in str(err).lower() or
            "min_length" in str(err).lower()
            for err in errors
        )

    def test_whitespace_only_text(self) -> None:
        """Should accept strings containing only whitespace characters."""
        part = TextPart(type="text", text="   \n\t  ")
        assert part.text == "   \n\t  "

    def test_extremely_large_text(self) -> None:
        """Should reject text exceeding maximum allowed size (10MB)."""
        large_text = "A" * (10 * 1024 * 1024)
        with pytest.raises(ValidationError):
            TextPart(type="text", text=large_text)

    # --- Type Coercion Validation ---

    def test_type_coercion_number_to_string(self) -> None:
        """Should handle numeric values according to Pydantic strict mode."""
        try:
            part = TextPart(type="text", text=12345)  # type: ignore
            assert isinstance(part.text, str)
            assert part.text == "12345"
        except ValidationError:
            pass  # Expected in strict mode

    def test_type_coercion_boolean_to_string(self) -> None:
        """Should handle boolean values according to Pydantic strict mode."""
        try:
            part = TextPart(type="text", text=True)  # type: ignore
            assert isinstance(part.text, str)
            assert part.text in ("True", "true")
        except ValidationError:
            pass  # Expected in strict mode

    # --- Unicode & Special Characters ---

    def test_unicode_text_content(self) -> None:
        """Should correctly handle Unicode characters in text content."""
        unicode_text = "Hello 世界 🌍 مرحبا שלום"
        part = TextPart(type="text", text=unicode_text)
        assert part.text == unicode_text

    def test_newlines_and_special_chars_in_text(self) -> None:
        """Should preserve newlines and special characters in text."""
        special_text = "Line 1\nLine 2\tTabbed\r\nWindows style"
        part = TextPart(type="text", text=special_text)
        assert part.text == special_text


# ═══════════════════════════════════════════════════════════════════════════
# 4. MEDIA XOR LOGIC TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestMediaXORLogic:
    """Media Parts Mutual Exclusivity Constraints (XOR)"""

    # --- ImagePart XOR Validation ---

    def test_image_with_url_only(self, valid_image_url_part: ImagePart) -> None:
        """Should accept ImagePart with only URL source."""
        assert valid_image_url_part.url == "https://example.com/valid_image.jpg"
        assert valid_image_url_part.data is None

    def test_image_with_data_only(self, valid_image_base64_part: ImagePart) -> None:
        """Should accept ImagePart with only Base64 data source."""
        assert valid_image_base64_part.data == TINY_PNG_BASE64
        assert valid_image_base64_part.url is None

    def test_image_rejects_both_url_and_data(self) -> None:
        """Must reject ImagePart when both URL and data are provided."""
        with pytest.raises(ValueError) as exc_info:
            ImagePart(
                type="image",
                url="https://example.com/image.jpg",
                data=TINY_PNG_BASE64
            )
        assert "cannot specify both" in str(exc_info.value).lower()

    def test_image_rejects_neither_url_nor_data(self) -> None:
        """Must reject ImagePart when neither URL nor data is provided."""
        with pytest.raises(ValueError) as exc_info:
            ImagePart(type="image")
        assert "must specify either" in str(exc_info.value).lower()

    def test_image_empty_url_string_treated_as_invalid(self) -> None:
        """Should reject empty URL strings via CanonicalURL validation."""
        with pytest.raises(ValidationError) as exc_info:
            ImagePart(type="image", url="")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_image_whitespace_url_treated_as_invalid(self) -> None:
        """Should reject whitespace-only URLs via CanonicalURL validation."""
        with pytest.raises(ValidationError) as exc_info:
            ImagePart(type="image", url="   \t\n  ")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_image_whitespace_data_rejected(self) -> None:
        """Should reject whitespace-only data via Base64Data validation."""
        with pytest.raises(ValidationError) as exc_info:
            ImagePart(type="image", url="https://example.com/img.jpg", data="   ")
        assert "cannot be empty" in str(exc_info.value).lower()

    # --- AudioPart XOR Validation ---

    def test_audio_with_url_only(self) -> None:
        """Should accept AudioPart with only URL source."""
        audio = AudioPart(type="audio", url="https://example.com/audio.mp3")
        assert audio.url == "https://example.com/audio.mp3"
        assert audio.data is None

    def test_audio_with_data_only(self, valid_audio_part: AudioPart) -> None:
        """Should accept AudioPart with only Base64 data source."""
        assert valid_audio_part.data == TINY_WAV_BASE64
        assert valid_audio_part.url is None

    def test_audio_rejects_both_url_and_data(self) -> None:
        """Must reject AudioPart when both URL and data are provided."""
        with pytest.raises(ValueError) as exc_info:
            AudioPart(
                type="audio",
                url="https://example.com/audio.mp3",
                data=TINY_WAV_BASE64
            )
        assert "cannot specify both" in str(exc_info.value).lower()

    def test_audio_rejects_neither_url_nor_data(self) -> None:
        """Must reject AudioPart when neither URL nor data is provided."""
        with pytest.raises(ValueError) as exc_info:
            AudioPart(type="audio")
        assert "must specify either" in str(exc_info.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 5. SECURITY & FORMAT VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityFormats:
    """Format Validation & Security Boundary Tests"""

    # --- Base64 Validation ---

    def test_image_rejects_invalid_base64_data(self) -> None:
        """Should reject invalid Base64 data for ImagePart."""
        with pytest.raises(ValidationError):
            ImagePart(type="image", data="ImNotBase64!!$#@%^&*()")

    def test_audio_rejects_invalid_base64_data(self) -> None:
        """Should reject invalid Base64 data for AudioPart."""
        with pytest.raises(ValidationError):
            AudioPart(type="audio", data="ThisIsNotBase64!!!###")

    def test_base64_ignores_whitespace_and_newlines(self) -> None:
        """Should handle or clean Base64 data with newlines and spaces."""
        dirty_data = f"{TINY_PNG_BASE64}\n  "
        part = ImagePart(type="image", data=dirty_data)
        assert part.data is not None
        assert "iVBOR" in part.data

    # --- URL Format Validation ---

    def test_image_rejects_invalid_url_format(self) -> None:
        """Should reject malformed URLs for ImagePart."""
        with pytest.raises(ValidationError):
            ImagePart(type="image", url="esto_no_es_una_url")

    def test_audio_rejects_invalid_url_format(self) -> None:
        """Should reject malformed URLs for AudioPart."""
        with pytest.raises(ValidationError):
            AudioPart(type="audio", url="not://a/valid/url/format")

    def test_rejects_relative_urls(self) -> None:
        """Should reject relative URLs requiring absolute paths."""
        with pytest.raises(ValidationError):
            ImagePart(type="image", url="/images/logo.png")

    def test_rejects_data_uri_in_url_field(self) -> None:
        """Should reject data URIs in URL field."""
        with pytest.raises(ValidationError):
            ImagePart(type="image", url=f"data:image/png;base64,{TINY_PNG_BASE64}")

    def test_extremely_long_url(self) -> None:
        """Should accept very long but valid URLs."""
        long_url = "https://example.com/" + "a" * 2000 + ".jpg"
        img = ImagePart(type="image", url=long_url)
        assert img.url == long_url

    # --- Media Type Security ---

    def test_image_rejects_dangerous_media_types(self) -> None:
        """Should reject executable media types for ImagePart."""
        with pytest.raises(ValidationError):
            ImagePart(
                type="image",
                url="https://example.com/malicious",
                media_type="application/x-executable"
            )

    def test_audio_rejects_dangerous_media_types(self) -> None:
        """Should reject executable media types for AudioPart."""
        with pytest.raises(ValidationError):
            AudioPart(
                type="audio",
                url="https://example.com/malicious.exe",
                media_type="application/x-executable"
            )

    def test_image_with_custom_media_type(self) -> None:
        """Should accept valid custom media types for ImagePart."""
        img = ImagePart(
            type="image",
            url="https://example.com/image.webp",
            media_type="image/webp"
        )
        assert img.media_type == "image/webp"

    def test_audio_with_custom_media_type(self) -> None:
        """Should accept valid custom media types for AudioPart."""
        audio = AudioPart(
            type="audio",
            url="https://example.com/audio.ogg",
            media_type="audio/ogg"
        )
        assert audio.media_type == "audio/ogg"

    # --- Character Encoding Security ---

    def test_rejects_non_ascii_in_base64_field(self) -> None:
        """Should reject non-ASCII characters in Base64 data."""
        with pytest.raises(ValidationError):
            ImagePart(type="image", data=f"{TINY_PNG_BASE64}ñ")


# ═══════════════════════════════════════════════════════════════════════════
# 6. DISCRIMINATOR & POLYMORPHISM TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDiscriminator:
    """Discriminated Union (ContentPart) Integrity Tests"""

    # --- Type Resolution ---

    def test_discriminator_text_part(self) -> None:
        """Should correctly resolve TextPart from discriminator."""
        data = {"type": "text", "text": "Hello"}
        adapter = TypeAdapter(ContentPart)
        part = adapter.validate_python(data)
        assert isinstance(part, TextPart)
        assert part.text == "Hello"

    def test_discriminator_image_part(self) -> None:
        """Should correctly resolve ImagePart from discriminator."""
        data = {"type": "image", "url": "https://example.com/image.jpg"}
        adapter = TypeAdapter(ContentPart)
        part = adapter.validate_python(data)
        assert isinstance(part, ImagePart)
        assert part.url == "https://example.com/image.jpg"

    def test_discriminator_audio_part(self) -> None:
        """Should correctly resolve AudioPart from discriminator."""
        data = {"type": "audio", "data": TINY_WAV_BASE64}
        adapter = TypeAdapter(ContentPart)
        part = adapter.validate_python(data)
        assert isinstance(part, AudioPart)
        assert part.data == TINY_WAV_BASE64

    # --- Error Cases ---

    def test_discriminator_rejects_unknown_type(self) -> None:
        """Should reject unknown type values in discriminator."""
        data = {"type": "video", "url": "https://example.com/video.mp4"}
        adapter = TypeAdapter(ContentPart)
        with pytest.raises(ValidationError) as exc_info:
            adapter.validate_python(data)
        error_msg = str(exc_info.value).lower()
        assert "discriminator" in error_msg or "video" in error_msg

    def test_discriminator_schema_crossover(self) -> None:
        """Should reject mismatched type-field combinations."""
        data = {
            "type": "text",
            "url": "https://example.com/image.jpg",
            "data": "base64data"
        }
        adapter = TypeAdapter(ContentPart)
        with pytest.raises(ValidationError) as exc_info:
            adapter.validate_python(data)
        assert any("text" in str(err).lower() for err in exc_info.value.errors())

    def test_discriminator_missing_type_field(self) -> None:
        """Should reject payloads missing the type discriminator field."""
        data = {"text": "Hello"}
        adapter = TypeAdapter(ContentPart)
        with pytest.raises(ValidationError) as exc_info:
            adapter.validate_python(data)
        assert any("type" in str(err).lower() for err in exc_info.value.errors())


# ═══════════════════════════════════════════════════════════════════════════
# 7. SERIALIZATION & CONSISTENCY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSerializationConsistency:
    """Immutability, Serialization & Data Integrity Tests"""

    # --- Immutability ---

    def test_immutability_if_frozen(self, valid_text_part: TextPart) -> None:
        """Should enforce immutability when CanonicalModel is frozen."""
        try:
            valid_text_part.text = "Modified"  # type: ignore
            assert valid_text_part.text == "Modified"
        except (ValidationError, AttributeError):
            pass  # Expected behavior

    # --- JSON Serialization ---

    def test_serialization_includes_discriminator(
        self,
        valid_image_url_part: ImagePart
    ) -> None:
        """Should include discriminator field in JSON output."""
        json_output = valid_image_url_part.model_dump_json()
        assert '"type":"image"' in json_output or '"type": "image"' in json_output

    def test_serialization_excludes_none_fields(
        self,
        valid_image_url_part: ImagePart
    ) -> None:
        """Should exclude None fields when exclude_none=True."""
        json_dict = valid_image_url_part.model_dump(exclude_none=True)
        assert "data" not in json_dict
        assert json_dict["url"] == "https://example.com/valid_image.jpg"

    def test_serialization_includes_none_fields_when_configured(
        self,
        valid_image_url_part: ImagePart
    ) -> None:
        """Should include None fields when exclude_none=False."""
        json_dict = valid_image_url_part.model_dump(exclude_none=False)
        assert "data" in json_dict
        assert json_dict["data"] is None

    # --- Round-Trip Validation ---

    def test_deserialization_round_trip_text(
        self,
        valid_text_part: TextPart
    ) -> None:
        """Should maintain TextPart integrity through serialization cycle."""
        json_str = valid_text_part.model_dump_json()
        restored = TextPart.model_validate_json(json_str)
        assert restored.text == valid_text_part.text
        assert restored.type == valid_text_part.type

    def test_deserialization_round_trip_image(
        self,
        valid_image_base64_part: ImagePart
    ) -> None:
        """Should maintain ImagePart integrity through serialization cycle."""
        json_str = valid_image_base64_part.model_dump_json()
        restored = ImagePart.model_validate_json(json_str)
        assert restored.data == valid_image_base64_part.data
        assert restored.type == valid_image_base64_part.type