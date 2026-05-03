"""
Multimodal content primitives for message composition.

This module defines the atomic building blocks for multimodal messages: text,
images, and audio. Each content part is a discriminated union member that can
be combined in message content arrays to support rich interactions.

Security Features:
    - MIME type allowlists prevent arbitrary file uploads.
    - Mutual exclusivity (data XOR url) prevents ambiguous sources.
    - Base64Data and SafeURL types enforce format validity.
    - Empty content is rejected to prevent protocol pollution.

Classes:
    TextPart: Plain text content fragment
    ImagePart: Visual data (base64 or URL)
    AudioPart: Audio data (base64 or URL)

Type Aliases:
    ContentPart: Discriminated union of all content types

Enums:
    ContentType: Discriminates between multimodal content types
"""

from __future__ import annotations

from typing import Literal, Annotated, Any
from enum import Enum

from pydantic import Field, field_validator, model_validator

from xulcan.core.primitives import (
    ImmutableRecord,
    MimeType,
    SemanticText,
    SafeURL,
    Base64Data,
)


# =============================================================================
# CONSTANTS & SECURITY BOUNDARIES
# =============================================================================

SAFE_IMAGE_MIMES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml"  # Note: SVG can contain scripts. Downstream must sanitize.
})
"""Allowed MIME types for image content to prevent executable uploads."""

SAFE_AUDIO_MIMES = frozenset({
    "audio/wav",
    "audio/mp3",
    "audio/ogg",
    "audio/mpeg",
    "audio/webm"
})
"""Allowed MIME types for audio content to prevent executable uploads."""


# =============================================================================
# DOMAIN ENUMERATIONS
# =============================================================================

class ContentType(str, Enum):
    """Discriminates between multimodal content types.

    Enables type-safe handling of text vs. binary media without runtime checks.

    Attributes:
        TEXT: Plain text content.
        IMAGE: Visual data (image).
        AUDIO: Audio data (sound).
    """
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


# =============================================================================
# MULTIMODAL CONTENT PRIMITIVES
# =============================================================================

class TextPart(ImmutableRecord):
    """A content fragment containing plain text.

    The simplest multimodal building block. Used in messages where text is
    combined with images or audio. The min_length=1 constraint prevents
    empty text parts from polluting the content array.

    Attributes:
        type: Discriminator field (always "text").
        text: The textual content (validated by SemanticText base type).

    Example:
        >>> part = TextPart(type="text", text="Describe this image:")
    """
    type: Literal[ContentType.TEXT] = ContentType.TEXT
    text: SemanticText = Field(
        min_length=1,
        description="The text content (protected against DoS by SemanticText constraints)."
    )

    @field_validator("text", mode="after")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        """Reject inputs that are only whitespace while preserving formatting.

        We must allow newlines and leading/trailing whitespace to remain in
        stored text, but a value containing only whitespace provides no
        semantic content and should be rejected.

        Args:
            value: The text value to validate.

        Returns:
            The validated text value.

        Raises:
            ValueError: If the value is empty or contains only whitespace.
        """
        if not value.strip():
            raise ValueError("TextPart.text cannot be empty or whitespace-only.")
        return value


class ImagePart(ImmutableRecord):
    """A content fragment representing visual data.

    Images can be provided either as base64-encoded data (for small images or
    when URL hosting is unavailable) or as public URLs (for large images or
    when bandwidth is constrained). This class enforces mutual exclusivity
    to prevent ambiguity about which source to use.

    Security Boundaries:
        - MIME type allowlist prevents arbitrary file types (e.g., executables).
        - Exactly one source (data XOR url) prevents double-fetch attacks.
        - Base64Data and SafeURL types enforce format validity.

    Attributes:
        type: Discriminator field (always "image").
        media_type: MIME type from allowlist (default: "image/jpeg").
        data: Base64-encoded image bytes (without data URI prefix).
        url: Public URL to image resource.

    Example:
        >>> # From URL
        >>> img = ImagePart(
        ...     type="image",
        ...     url="https://example.com/photo.jpg"
        ... )
        >>>
        >>> # From base64
        >>> img = ImagePart(
        ...     type="image",
        ...     media_type="image/png",
        ...     data="iVBORw0KGgoAAAANSUhEUgAAAAUA..."
        ... )
    """
    type: Literal[ContentType.IMAGE] = ContentType.IMAGE
    media_type: MimeType = Field(
        default="image/jpeg",
        description="MIME type constrained to safe image formats."
    )
    data: Base64Data | None = Field(
        default=None,
        description="Base64-encoded image data (excludes data URI scheme prefix)."
    )
    url: SafeURL | None = Field(
        default=None,
        description="Public URL to image resource."
    )

    @field_validator("url", mode="before")
    @classmethod
    def coerce_url_dict(cls, value: Any) -> Any:
        """Accept a dict wrapper like {'url': 'https://...'} for fixtures.

        Tests sometimes pass url as a small mapping. Allow that shape and
        extract the inner string to satisfy the `SafeURL` annotated type.

        Args:
            value: The value to coerce (may be a dict or string).

        Returns:
            The extracted URL string if value is a dict, otherwise the original value.
        """
        if isinstance(value, dict) and "url" in value:
            return value["url"]
        return value

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data_dict_or_datauri(cls, value: Any) -> Any:
        """Accept dict wrappers and extract base64 from data URIs.

        Fixtures may provide a data URI (e.g. 'data:image/png;base64,...')
        or a dict container with key 'url'. Strip prefixes and return only
        the raw base64 payload expected by `Base64Data`.

        Args:
            value: The value to coerce (may be a dict, data URI, or string).

        Returns:
            The extracted base64 string after stripping prefixes.
        """
        if isinstance(value, dict) and "url" in value:
            value = value["url"]

        if isinstance(value, str) and value.startswith("data:"):
            # Format: data:<mediatype>;base64,<data>
            return value.split(",", 1)[-1]

        return value

    @field_validator("media_type", mode="after")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        """Enforces MIME type allowlist to prevent arbitrary file uploads.

        Args:
            value: The MIME type string to validate.

        Returns:
            The normalized lowercase MIME type.

        Raises:
            ValueError: If the MIME type is not in the safe image allowlist.
        """
        v_norm = value.strip().lower()
        if v_norm not in SAFE_IMAGE_MIMES:
            raise ValueError(
                f"Unsupported image MIME type: '{value}'. "
                f"Allowed types: {SAFE_IMAGE_MIMES}. "
                f"This restriction prevents upload of executable content."
            )
        return v_norm

    @model_validator(mode='after')
    def validate_source(self) -> ImagePart:
        """Ensures exactly one source is provided (data XOR url).

        Returns:
            ImagePart: The validated instance.

        Raises:
            ValueError: If neither or both sources are specified.
        """
        has_data = self.data is not None
        has_url = self.url is not None

        if not has_data and not has_url:
            raise ValueError(
                "ImagePart must specify either 'data' or 'url' source. "
                "Without a source, the image cannot be rendered."
            )

        if has_data and has_url:
            raise ValueError(
                "ImagePart cannot specify both 'data' and 'url'. "
                "Ambiguous sources prevent deterministic processing."
            )

        return self


class AudioPart(ImmutableRecord):
    """A content fragment representing audio data.

    Mirrors ImagePart design for audio media. Enforces MIME type safety and
    source exclusivity to prevent ambiguous interpretation.

    Attributes:
        type: Discriminator field (always "audio").
        media_type: MIME type from allowlist (default: "audio/wav").
        data: Base64-encoded audio bytes.
        url: Public URL to audio resource.

    Example:
        >>> audio = AudioPart(
        ...     type="audio",
        ...     media_type="audio/mp3",
        ...     url="https://example.com/speech.mp3"
        ... )
    """
    type: Literal[ContentType.AUDIO] = ContentType.AUDIO
    media_type: MimeType = Field(
        default="audio/wav",
        description="MIME type constrained to safe audio formats."
    )
    data: Base64Data | None = Field(
        default=None,
        description="Base64-encoded audio data."
    )
    url: SafeURL | None = Field(
        default=None,
        description="Public URL to audio file."
    )

    @field_validator("url", mode="before")
    @classmethod
    def coerce_url_dict(cls, value: Any) -> Any:
        """Accept a dict wrapper like {'url': 'https://...'} for fixtures.

        Args:
            value: The value to coerce (may be a dict or string).

        Returns:
            The extracted URL string if value is a dict, otherwise the original value.
        """
        if isinstance(value, dict) and "url" in value:
            return value["url"]
        return value

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data_dict_or_datauri(cls, value: Any) -> Any:
        """Accept dict wrappers and extract base64 from data URIs.

        Fixtures may provide a data URI (e.g. 'data:audio/wav;base64,...')
        or a dict container with key 'url'. Strip prefixes and return only
        the raw base64 payload expected by `Base64Data`.

        Args:
            value: The value to coerce (may be a dict, data URI, or string).

        Returns:
            The extracted base64 string after stripping prefixes.
        """
        if isinstance(value, dict) and "url" in value:
            value = value["url"]

        if isinstance(value, str) and value.startswith("data:"):
            return value.split(",", 1)[-1]

        return value

    @field_validator("media_type", mode="after")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        """Enforces MIME type allowlist for audio formats.

        Args:
            value: The MIME type string to validate.

        Returns:
            The normalized lowercase MIME type.

        Raises:
            ValueError: If the MIME type is not in the safe audio allowlist.
        """
        v_norm = value.strip().lower()
        if v_norm not in SAFE_AUDIO_MIMES:
            raise ValueError(
                f"Unsupported audio MIME type: '{value}'. "
                f"Allowed types: {SAFE_AUDIO_MIMES}. "
                f"This restriction prevents upload of executable content."
            )
        return v_norm

    @model_validator(mode='after')
    def validate_source(self) -> AudioPart:
        """Ensures exactly one source is provided (data XOR url).

        Returns:
            AudioPart: The validated instance.

        Raises:
            ValueError: If neither or both sources are specified.
        """
        has_data = self.data is not None
        has_url = self.url is not None

        if not has_data and not has_url:
            raise ValueError("AudioPart must specify either 'data' or 'url' source.")

        if has_data and has_url:
            raise ValueError(
                "AudioPart cannot specify both 'data' and 'url'. "
                "Ambiguous sources prevent deterministic processing."
            )

        return self


# =============================================================================
# TYPE ALIASES
# =============================================================================

# Discriminated union enabling type-safe polymorphism.
# Pydantic automatically routes to the correct class based on the 'type' field.
ContentPart = Annotated[
    TextPart | ImagePart | AudioPart,
    Field(discriminator='type')
]
