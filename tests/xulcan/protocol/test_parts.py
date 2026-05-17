"""Unit Tests for xulcan.protocol.parts module.

Test Suite Coverage:
    - Class 1: TextPart invariants and DoS prevention
    - Class 2: Media mutual exclusivity (XOR logic)
    - Class 3: Media security boundaries (MIME allowlists)
    - Class 4: Polymorphism and discriminated union resolution

Philosophy: Strict Type Safety, Defense in Depth, Zero-Trust Validation.
"""

import pytest
import json
from typing import Any, Dict
from pydantic import ValidationError, TypeAdapter

from tests.xulcan.conftest import valid_safe_url
from xulcan.protocol.parts import (
    TextPart,
    ImagePart,
    AudioPart,
    ContentPart,
    ContentType,
)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 1: TEXTPART INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════

class TestTextPartInvariants:
    """Validates TextPart content requirements and DoS prevention."""

    def test_construct_valid(self, valid_text_part: TextPart) -> None:
        """Should create TextPart with valid text and auto-assign type."""
        assert valid_text_part.type == "text"
        assert isinstance(valid_text_part.text, str)
        assert len(valid_text_part.text) > 0

    def test_uses_fixture(self, valid_text_part: TextPart) -> None:
        """Should accept fixture-provided TextPart."""
        assert valid_text_part.type == "text"
        assert isinstance(valid_text_part.text, str)
        assert len(valid_text_part.text) > 0

    def test_constraint_min_length(self) -> None:
        """Should raise ValidationError if text is empty string."""
        with pytest.raises(ValidationError) as exc:
            TextPart(text="")
        
        assert "at least 1 character" in str(exc.value).lower() or "min_length" in str(exc.value).lower()

    def test_constraint_whitespace_only(self) -> None:
        """Should reject whitespace-only text."""
        with pytest.raises(ValidationError):
            TextPart(text="   ")

    @pytest.mark.parametrize("invalid_value", [
        123,
        True,
        None,
        [],
        {},
    ])
    def test_reject_non_string_types(self, invalid_value: Any) -> None:
        """Should raise ValidationError if text is not a string."""
        with pytest.raises(ValidationError):
            TextPart(text=invalid_value)  # type: ignore

    def test_preserves_multiline_text(self) -> None:
        """Should preserve newlines and formatting in text."""
        multiline = "Line 1\nLine 2\n\tIndented"
        part = TextPart(text=multiline)
        
        assert part.text == multiline
        assert "\n" in part.text

    def test_accepts_unicode_content(self) -> None:
        """Should accept Unicode characters in text."""
        unicode_text = "Hello 世界 🌍 Привет"
        part = TextPart(text=unicode_text)
        
        assert part.text == unicode_text


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 2: MEDIA MUTUAL EXCLUSIVITY
# ═══════════════════════════════════════════════════════════════════════════

class TestImagePartMutualExclusivity:
    """Validates XOR enforcement for ImagePart sources."""

    def test_accepts_url_only(self, valid_safe_url: str) -> None:
        """Should accept ImagePart with only URL specified."""
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type="image/png"
        )
        
        assert part.url == valid_safe_url
        assert part.data is None

    def test_accepts_data_only(self, valid_base64_data: str) -> None:
        """Should accept ImagePart with only base64 data specified."""
        part = ImagePart(
            type="image",
            data=valid_base64_data,
            media_type="image/png"
        )
        
        assert part.data == valid_base64_data
        assert part.url is None

    def test_rejects_both_sources(
        self, 
        valid_safe_url: str, 
        valid_base64_data: str
    ) -> None:
        """Should raise ValidationError if both data and url are provided."""
        with pytest.raises(ValidationError) as exc:
            ImagePart(
                type="image",
                url=valid_safe_url,
                data=valid_base64_data,
                media_type="image/png"
            )
        
        assert "cannot specify both" in str(exc.value).lower() or "ambiguous" in str(exc.value).lower()

    def test_rejects_no_source(self) -> None:
        """Should raise ValidationError if neither data nor url provided."""
        with pytest.raises(ValidationError) as exc:
            ImagePart(
                type="image",
                media_type="image/png"
            )
        
        assert "must specify either" in str(exc.value).lower() or "source" in str(exc.value).lower()

    def test_uses_url_fixture(self, valid_image_part_url: ImagePart) -> None:
        """Should accept fixture-provided ImagePart with URL."""
        assert valid_image_part_url.url is not None
        assert valid_image_part_url.data is None

    def test_uses_base64_fixture(self, valid_image_part_base64: ImagePart) -> None:
        """Should accept fixture-provided ImagePart with base64."""
        assert valid_image_part_base64.data is not None
        assert valid_image_part_base64.url is None


class TestAudioPartMutualExclusivity:
    """Validates XOR enforcement for AudioPart sources."""

    def test_accepts_url_only(self, valid_safe_url: str) -> None:
        """Should accept AudioPart with only URL specified."""
        part = AudioPart(
            type="audio",
            url=valid_safe_url,
            media_type="audio/mp3"
        )
        
        assert part.url == valid_safe_url
        assert part.data is None

    def test_accepts_data_only(self, valid_base64_data: str) -> None:
        """Should accept AudioPart with only base64 data specified."""
        part = AudioPart(
            type="audio",
            data=valid_base64_data,
            media_type="audio/wav"
        )
        
        assert part.data == valid_base64_data
        assert part.url is None

    def test_rejects_both_sources(
        self, 
        valid_safe_url: str, 
        valid_base64_data: str
    ) -> None:
        """Should raise ValidationError if both data and url are provided."""
        with pytest.raises(ValidationError) as exc:
            AudioPart(
                type="audio",
                url=valid_safe_url,
                data=valid_base64_data,
                media_type="audio/ogg"
            )
        
        assert "cannot specify both" in str(exc.value).lower()

    def test_rejects_no_source(self) -> None:
        """Should raise ValidationError if neither data nor url provided."""
        with pytest.raises(ValidationError) as exc:
            AudioPart(
                type="audio",
                media_type="audio/webm"
            )
        
        assert "must specify either" in str(exc.value).lower()


class TestSerializationOptimization:
    """Validates that unused fields are excluded from serialization."""

    def test_url_based_excludes_data_field(self, valid_safe_url: str) -> None:
        """Should not serialize 'data' field when using URL source."""
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type="image/jpeg"
        )
        
        serialized = part.model_dump(exclude_none=True)
        assert "data" not in serialized
        assert serialized["url"] == valid_safe_url

    def test_data_based_excludes_url_field(self, valid_base64_data: str) -> None:
        """Should not serialize 'url' field when using data source."""
        part = ImagePart(
            type="image",
            data=valid_base64_data,
            media_type="image/png"
        )
        
        serialized = part.model_dump(exclude_none=True)
        assert "url" not in serialized
        assert serialized["data"] == valid_base64_data


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 3: MEDIA SECURITY BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════

class TestImagePartSecurityBoundaries:
    """Validates MIME type allowlist enforcement for images."""

    @pytest.mark.parametrize("safe_mime", [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    ])
    def test_accepts_safe_mime_types(
        self, 
        safe_mime: str, 
        valid_safe_url: str
    ) -> None:
        """Should accept all MIME types in the allowlist."""
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type=safe_mime
        )
        
        assert part.media_type == safe_mime

    @pytest.mark.parametrize("dangerous_mime", [
        "application/x-executable",
        "text/html",
        "application/javascript",
        "text/javascript",
        "application/octet-stream",
        "image/x-icon",  # Not in allowlist
        "video/mp4",     # Wrong category
    ])
    def test_rejects_unsafe_mime_types(
        self, 
        dangerous_mime: str, 
        valid_safe_url: str
    ) -> None:
        """Should reject MIME types not in the allowlist."""
        with pytest.raises(ValidationError) as exc:
            ImagePart(
                type="image",
                url=valid_safe_url,
                media_type=dangerous_mime
            )
        
        assert "unsupported" in str(exc.value).lower() or "allowed" in str(exc.value).lower()

    def test_mime_consistency_prevents_audio_in_image(self, valid_safe_url: str) -> None:
        """Should reject audio MIME type in ImagePart."""
        with pytest.raises(ValidationError):
            ImagePart(
                type="image",
                url=valid_safe_url,
                media_type="audio/wav"
            )

    def test_default_mime_type(self, valid_safe_url: str) -> None:
        """Should use default MIME type 'image/jpeg' if not specified."""
        part = ImagePart(
            type="image",
            url=valid_safe_url
        )
        
        assert part.media_type == "image/jpeg"


class TestAudioPartSecurityBoundaries:
    """Validates MIME type allowlist enforcement for audio."""

    @pytest.mark.parametrize("safe_mime", [
        "audio/wav",
        "audio/mp3",
        "audio/ogg",
        "audio/mpeg",
        "audio/webm",
    ])
    def test_accepts_safe_mime_types(
        self, 
        safe_mime: str, 
        valid_safe_url: str
    ) -> None:
        """Should accept all MIME types in the allowlist."""
        part = AudioPart(
            type="audio",
            url=valid_safe_url,
            media_type=safe_mime
        )
        
        assert part.media_type == safe_mime

    @pytest.mark.parametrize("dangerous_mime", [
        "application/x-executable",
        "text/html",
        "video/mp4",
        "image/png",  # Wrong category
        "audio/flac", # Not in allowlist
    ])
    def test_rejects_unsafe_mime_types(
        self, 
        dangerous_mime: str, 
        valid_safe_url: str
    ) -> None:
        """Should reject MIME types not in the allowlist."""
        with pytest.raises(ValidationError) as exc:
            AudioPart(
                type="audio",
                url=valid_safe_url,
                media_type=dangerous_mime
            )
        
        assert "unsupported" in str(exc.value).lower() or "allowed" in str(exc.value).lower()

    def test_default_mime_type(self, valid_safe_url: str) -> None:
        """Should use default MIME type 'audio/wav' if not specified."""
        part = AudioPart(
            type="audio",
            url=valid_safe_url
        )
        
        assert part.media_type == "audio/wav"


class TestURLSafetyDelegation:
    """Validates that URL validation is delegated to SafeURL primitive."""

    def test_rejects_javascript_protocol(self) -> None:
        """Should reject javascript: URLs that could execute code."""
        with pytest.raises(ValidationError):
            ImagePart(
                type="image",
                url="javascript:alert(1)",
                media_type="image/png"
            )

    def test_rejects_data_uri_in_url_field(self) -> None:
        """Should reject data URIs in url field (use data field instead)."""
        with pytest.raises(ValidationError):
            ImagePart(
                type="image",
                url="data:image/png;base64,iVBORw0KGgo=",
                media_type="image/png"
            )

    def test_accepts_https_urls(self, valid_safe_url: str) -> None:
        """Should accept secure HTTPS URLs."""
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type="image/png"
        )
        
        assert part.url == valid_safe_url


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 4: POLYMORPHISM AND DISCRIMINATOR
# ═══════════════════════════════════════════════════════════════════════════

class TestContentTypeEnum:
    """Validates ContentType enum values."""

    def test_enum_values_match_spec(self) -> None:
        """Should have exact string values for wire protocol."""
        assert ContentType.TEXT.value == "text"
        assert ContentType.IMAGE.value == "image"
        assert ContentType.AUDIO.value == "audio"

    def test_enum_members_are_strings(self) -> None:
        """Should be string enum for JSON serialization."""
        for content_type in ContentType:
            assert isinstance(content_type.value, str)


class TestDiscriminatedUnionResolution:
    """Validates Pydantic discriminated union routing via 'type' field."""

    def test_adapter_resolution_text(self, valid_text_part: TextPart) -> None:
        """Should resolve to TextPart when type='text'."""
        payload = {"type": "text", "text": valid_text_part.text}
        adapter = TypeAdapter(ContentPart)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, TextPart)
        assert result.type == "text"
        assert result.text == valid_text_part.text

    def test_adapter_resolution_image_url(self, valid_safe_url: str) -> None:
        """Should resolve to ImagePart when type='image'."""
        payload = {
            "type": "image",
            "url": valid_safe_url,
            "media_type": "image/png"
        }
        adapter = TypeAdapter(ContentPart)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, ImagePart)
        assert result.type == "image"
        assert result.url == valid_safe_url

    def test_adapter_resolution_image_data(self, valid_base64_data: str) -> None:
        """Should resolve to ImagePart with base64 data."""
        payload = {
            "type": "image",
            "data": valid_base64_data,
            "media_type": "image/jpeg"
        }
        adapter = TypeAdapter(ContentPart)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, ImagePart)
        assert result.data == valid_base64_data

    def test_adapter_resolution_audio(self, valid_safe_url: str) -> None:
        """Should resolve to AudioPart when type='audio'."""
        payload = {
            "type": "audio",
            "url": valid_safe_url,
            "media_type": "audio/mp3"
        }
        adapter = TypeAdapter(ContentPart)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, AudioPart)
        assert result.type == "audio"

    def test_missing_discriminator(self, valid_safe_url: str) -> None:
        """Should raise ValidationError if 'type' field is missing."""
        payload = {
            "url": valid_safe_url,
            "media_type": "image/png"
        }
        adapter = TypeAdapter(ContentPart)
        
        with pytest.raises(ValidationError) as exc:
            adapter.validate_python(payload)
        
        assert "discriminator" in str(exc.value).lower() or "type" in str(exc.value).lower()

    def test_invalid_discriminator(self, valid_safe_url: str) -> None:
        """Should raise ValidationError for unsupported content type."""
        payload = {
            "type": "video",
            "url": valid_safe_url
        }
        adapter = TypeAdapter(ContentPart)
        
        with pytest.raises(ValidationError) as exc:
            adapter.validate_python(payload)
        
        assert "video" in str(exc.value).lower() or "discriminator" in str(exc.value).lower()


class TestJSONRoundtripIntegrity:
    """Validates serialization and deserialization maintain data integrity."""

    def test_roundtrip_text_part(self, valid_text_part: TextPart) -> None:
        """Should maintain integrity through JSON roundtrip for TextPart."""
        # Serialize to JSON
        json_str = valid_text_part.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        # Deserialize back
        adapter = TypeAdapter(ContentPart)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, TextPart)
        assert reconstructed.text == valid_text_part.text
        assert reconstructed.type == valid_text_part.type

    def test_roundtrip_image_part_url(self, valid_image_part_url: ImagePart) -> None:
        """Should maintain integrity through JSON roundtrip for ImagePart."""
        json_str = valid_image_part_url.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(ContentPart)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, ImagePart)
        assert reconstructed.url == valid_image_part_url.url
        assert reconstructed.media_type == valid_image_part_url.media_type

    def test_roundtrip_audio_part_data(self, valid_base64_data: str) -> None:
        """Should maintain integrity through JSON roundtrip for AudioPart."""
        original = AudioPart(
            data=valid_base64_data,
            media_type="audio/ogg"
        )
        
        json_str = original.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(ContentPart)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, AudioPart)
        assert reconstructed.data == original.data
        assert reconstructed.media_type == original.media_type

    def test_serialized_format_matches_api_spec(self, valid_safe_url: str) -> None:
        """Should produce API-compatible JSON structure."""
        part = ImagePart(
            url=valid_safe_url,
            media_type="image/png"
        )
        
        serialized = part.model_dump()
        
        assert serialized["type"] == "image"
        assert "url" in serialized
        assert "media_type" in serialized
        # Ensure data is not present when using URL
        assert serialized.get("data") is None


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES AND BOUNDARY CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Validates handling of edge cases and boundary conditions."""

    def test_text_part_with_maximum_length(self) -> None:
        """Should accept very long text content."""
        long_text = "A" * 10000  # 10K characters
        part = TextPart(text=long_text)
        
        assert len(part.text) == 10000

    def test_base64_data_format_validation(self, valid_base64_data: str) -> None:
        """Should validate base64 encoding format."""
        valid_part = ImagePart(
            type="image",
            data=valid_base64_data,
            media_type="image/png"
        )
        assert valid_part.data is not None

    def test_case_sensitivity_normalization(self, valid_safe_url: str) -> None:
        """Should automatically normalize MIME types to lowercase per RFC."""
        
        # ACT: Instanciamos con mayúsculas
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type="IMAGE/PNG"  # uppercase input
        )

        # ASSERT: Verificamos que el sistema lo "limpió" por nosotros
        assert part.media_type == "image/png"  # lowercase storage
        
        # Opcional: Verificar que NO es igual a la entrada original
        assert part.media_type != "IMAGE/PNG"

    def test_svg_mime_type_accepted_despite_script_risk(self, valid_safe_url: str) -> None:
        """Should accept SVG MIME type even though it can contain scripts."""
        # This is intentionally allowed - downstream must sanitize
        part = ImagePart(
            type="image",
            url=valid_safe_url,
            media_type="image/svg+xml"
        )
        
        assert part.media_type == "image/svg+xml"