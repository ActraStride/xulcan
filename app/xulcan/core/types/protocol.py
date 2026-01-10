"""Standardized types for model interactions with Defense-in-Depth validation.

This module establishes a provider-agnostic contract for generative model
interactions, enforcing strict type safety and immutability. It implements
defensive validation to protect against malformed payloads, injection attacks,
and resource exhaustion (DoS) from untrusted inputs.

Key architectural principles:
1. **Input Sanitization**: All external data undergoes multi-layer validation
   before entering the system, preventing injection attacks and memory bombs.
2. **Canonical Types**: Leverages base types (CanonicalIdentifier, SemanticText)
   that enforce domain constraints at the type level.
3. **Discriminated Unions**: Uses Pydantic's discriminator pattern to enable
   type-safe polymorphism without runtime isinstance() checks.
4. **Recursion Protection**: Limits nesting depth to prevent stack overflow
   from maliciously crafted JSON structures.
"""

import json
import keyword
from typing import Any, Dict, List, Literal, Optional, Union, Annotated
from enum import Enum

from pydantic import Field, field_validator, model_validator

from .base import (
    CanonicalRecord, 
    UsageStats,
    CanonicalIdentifier,
    HumanLabel,
    SemanticText,
    CanonicalURL,
    Base64Data,
)


# ═══════════════════════════════════════════════════════════════════════════
# DEFENSIVE UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _validate_recursion_depth(
    data: Any, 
    current_depth: int = 0, 
    max_depth: int = 20
) -> None:
    """Enforces maximum nesting depth to prevent stack overflow attacks.
    
    Protects against 'JSON bombs' and maliciously crafted payloads that
    exploit recursive parsing algorithms. A depth of 20 is sufficient for
    legitimate use cases while preventing exponential memory allocation.
    
    Args:
        data: The structure to inspect (dict, list, or primitive).
        current_depth: Internal recursion counter (do not set manually).
        max_depth: Maximum allowed nesting levels.
            • 20 levels: Prevents stack overflow on typical Python runtimes.
            • Changing this value affects memory safety guarantees.
    
    Raises:
        ValueError: If nesting exceeds max_depth.
    """
    if current_depth > max_depth:
        raise ValueError(
            f"Data structure exceeds maximum nesting depth of {max_depth}. "
            f"This may indicate a malicious payload or corrupted data."
        )
    
    if isinstance(data, dict):
        for value in data.values():
            _validate_recursion_depth(value, current_depth + 1, max_depth)
    elif isinstance(data, list):
        for item in data:
            _validate_recursion_depth(item, current_depth + 1, max_depth)


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN ENUMERATIONS (Internal Type Safety)
# ═══════════════════════════════════════════════════════════════════════════

class Role(str, Enum):
    """Defines valid message roles in a conversation.
    
    These roles enforce the protocol contract between user, system, assistant,
    and tool execution layers. Not exported publicly to prevent external misuse.
    """
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(str, Enum):
    """Enumerates why a model generation terminated.
    
    Used for telemetry, debugging, and enforcing correct handling of incomplete
    responses (e.g., length limits require continuation logic).
    """
    STOP = "stop"                    # Natural completion
    LENGTH = "length"                # Hit token/character limit
    TOOL_CALLS = "tool_calls"        # Model requested tool execution
    CONTENT_FILTER = "content_filter"  # Safety filter triggered
    UNKNOWN = "unknown"              # Fallback for provider-specific reasons


class ContentType(str, Enum):
    """Discriminates between multimodal content types.
    
    Enables type-safe handling of text vs. binary media without runtime checks.
    """
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class ToolChoiceType(str, Enum):
    """Defines tool invocation strategies for model guidance.
    
    - AUTO: Model decides whether to use tools based on context.
    - NONE: Model must respond without tool calls.
    - REQUIRED: Model must call at least one tool (prevents direct responses).
    - FUNCTION: Explicit function selection (see NamedToolChoice).
    """
    AUTO = "auto"
    NONE = "none"
    REQUIRED = "required"
    FUNCTION = "function"


# ═══════════════════════════════════════════════════════════════════════════
# TOOL INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class ToolCall(CanonicalRecord):
    """Represents a model's request to execute an external function.
    
    This class encapsulates the intent-to-execute, not the execution result.
    Tool calls must be traceable (via unique ID) and must carry serializable
    arguments to prevent injection attacks when passed to execution contexts.
    
    Security Guarantees:
        - IDs are validated to be non-empty for traceability.
        - Arguments are strictly JSON-serializable (no arbitrary objects).
        - Recursion depth is bounded to prevent memory exhaustion.
    
    Attributes:
        id: Provider-generated unique identifier for correlation with ToolMessage.
        name: Function identifier (validated as CanonicalIdentifier).
        arguments: JSON-serializable dictionary of function parameters.
    
    Example:
        >>> call = ToolCall(
        ...     id="call_abc123",
        ...     name="get_weather",
        ...     arguments={"location": "San Francisco", "units": "celsius"}
        ... )
    """
    id: str = Field(
        description="Unique identifier for tracing this tool call through the system"
    )
    name: CanonicalIdentifier = Field(
        description="Function name to execute (must be valid identifier)"
    )
    arguments: Dict[str, Any] = Field(
        description="Function arguments as JSON-serializable dictionary"
    )

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        """Ensures traceability by rejecting empty or whitespace-only IDs.
        
        Without a valid ID, we cannot correlate ToolMessage responses back
        to their originating ToolCall, breaking the request-response chain.
        """
        if not v or not v.strip():
            raise ValueError(
                "Tool call ID cannot be empty. IDs are required for "
                "correlating tool execution results with requests."
            )
        return v

    @field_validator("arguments")
    @classmethod
    def validate_arguments_serializable(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Enforces strict JSON serializability and recursion limits.
        
        Rationale:
            - JSON serializability prevents injection of arbitrary Python objects
              that could execute code during serialization (e.g., __reduce__).
            - Recursion limits prevent stack overflow from deeply nested structures.
        
        Raises:
            ValueError: If arguments contain non-serializable data or exceed depth.
        """
        try:
            json.dumps(v)
        except (TypeError, OverflowError) as e:
            raise ValueError(
                f"Tool arguments must be JSON-serializable. Found: {type(e).__name__}: {str(e)}"
            )
        
        _validate_recursion_depth(v)
        return v


class FunctionDef(CanonicalRecord):
    """Defines a callable function exposed to the model.
    
    This specification allows the model to understand what tools are available
    and how to invoke them. The parameters field must conform to JSON Schema
    to enable automatic validation and type coercion in execution contexts.
    
    Invariants:
        - Function names cannot be Python keywords (prevents eval() injection).
        - Parameters schema must be valid JSON (no circular references).
        - Schema recursion is bounded to prevent parsing attacks.
    
    Attributes:
        name: Function identifier (validated as safe identifier, not a keyword).
        description: Human-readable explanation of function behavior.
        parameters: JSON Schema (draft-07) defining expected arguments.
    
    Example:
        >>> func = FunctionDef(
        ...     name="search_web",
        ...     description="Searches the web for a given query",
        ...     parameters={
        ...         "type": "object",
        ...         "properties": {
        ...             "query": {"type": "string"},
        ...             "max_results": {"type": "integer", "default": 10}
        ...         },
        ...         "required": ["query"]
        ...     }
        ... )
    """
    name: CanonicalIdentifier = Field(
        description="Function name (must be valid Python identifier)"
    )
    description: Optional[SemanticText] = Field(
        default=None,
        description="Human-readable description for model context"
    )
    parameters: Dict[str, Any] = Field(
        description="JSON Schema (draft-07) defining function parameters"
    )

    @field_validator("name")
    @classmethod
    def validate_python_keywords(cls, v: str) -> str:
        """Prevents usage of reserved keywords as function names.
        
        If we allowed keywords like 'def', 'class', or 'import' as function
        names, downstream code generation or eval() contexts could execute
        arbitrary Python code. This validator enforces safe naming.
        """
        if keyword.iskeyword(v):
            raise ValueError(
                f"Function name '{v}' is a reserved Python keyword. "
                f"This could enable code injection in execution contexts."
            )
        return v

    @field_validator("parameters")
    @classmethod
    def validate_parameters_schema(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validates JSON Schema safety and serializability.
        
        Protection Mechanisms:
            1. Type check: Ensures parameters is a dictionary.
            2. Serializability: Detects cyclic references via json.dumps().
            3. Recursion depth: Prevents stack overflow from nested schemas.
        
        Note: Changing max_depth in _validate_recursion_depth affects what
        schemas are considered valid. Deep nesting may indicate malicious intent.
        """
        if not isinstance(v, dict):
            raise ValueError(
                "Parameters must be a dictionary conforming to JSON Schema."
            )
        
        try:
            json.dumps(v)
        except RecursionError:
            raise ValueError(
                "Parameters schema contains cyclic references. "
                "This violates JSON Schema specifications."
            )
        except TypeError as e:
            raise ValueError(
                f"Parameters schema is not JSON serializable: {str(e)}"
            )
        
        _validate_recursion_depth(v)
            
        return v


class ToolDefinition(CanonicalRecord):
    """Wraps a FunctionDef in a standardized tool container.
    
    Provides a consistent interface for tool registration across providers.
    The 'type' field is currently fixed to "function" but allows future
    extension to other tool types (e.g., "code_interpreter", "retrieval").
    
    Attributes:
        type: Tool category (currently only "function" is supported).
        function: The function specification.
    """
    type: Literal["function"] = "function"
    function: FunctionDef


class NamedToolChoice(CanonicalRecord):
    """Forces the model to call a specific function.
    
    Used when the conversation context requires a deterministic tool invocation
    (e.g., "always call validate_input before proceeding"). This class enforces
    strict validation to prevent injection of malicious function names.
    
    Strict Mode Rationale:
        Only the 'name' key is allowed in the function dictionary. Extra keys
        could carry metadata that downstream systems misinterpret as executable
        instructions, leading to privilege escalation.
    
    Attributes:
        type: Discriminator (always "function").
        function: Dictionary containing exactly one key: 'name'.
    
    Example:
        >>> choice = NamedToolChoice(
        ...     type="function",
        ...     function={"name": "validate_input"}
        ... )
    """
    type: Literal["function"] = "function"
    function: Dict[str, str] = Field(
        description="Must contain exactly 'name' key with valid function identifier"
    )

    @field_validator("function")
    @classmethod
    def validate_function_dict(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Enforces strict structure and prevents extraneous keys.
        
        Validation Steps:
            1. Presence: 'name' key must exist.
            2. Non-empty: 'name' value cannot be empty/whitespace.
            3. Identifier Safety: 'name' must be a valid Python identifier.
            4. Strict Mode: No additional keys allowed (prevents metadata injection).
        
        Security Impact:
            Allowing extra keys could enable attackers to pass execution hints
            (e.g., {"name": "safe_func", "sudo": true}) that bypass authorization.
        """
        if "name" not in v:
            raise ValueError(
                "NamedToolChoice function dict must contain 'name' key for "
                "identifying which function to call."
            )
        
        name_value = v["name"]
        
        if not name_value or not name_value.strip():
            raise ValueError(
                "Function name cannot be empty. An empty name would make the "
                "tool call unroutable."
            )
        
        if not name_value.isidentifier():
            raise ValueError(
                f"Function name '{name_value}' is not a valid Python identifier. "
                f"This prevents safe mapping to executable code."
            )

        allowed_keys = {"name"}
        extra_keys = set(v.keys()) - allowed_keys
        if extra_keys:
            raise ValueError(
                f"Unexpected keys in NamedToolChoice function: {extra_keys}. "
                f"Only 'name' is permitted to prevent metadata injection attacks."
            )

        return v


ToolChoice = Union[ToolChoiceType, NamedToolChoice]
# Union representing either:
#   - A mode string ("auto", "none", "required")
#   - A specific function selection (NamedToolChoice)


# ═══════════════════════════════════════════════════════════════════════════
# MULTIMODAL CONTENT PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

class TextPart(CanonicalRecord):
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
    type: Literal["text"] = "text"
    text: SemanticText = Field(
        min_length=1,
        description="The text content (protected against DoS by SemanticText constraints)"
    )


class ImagePart(CanonicalRecord):
    """A content fragment representing visual data.
    
    Images can be provided either as base64-encoded data (for small images or
    when URL hosting is unavailable) or as public URLs (for large images or
    when bandwidth is constrained). This class enforces mutual exclusivity
    to prevent ambiguity about which source to use.
    
    Security Boundaries:
        - MIME type allowlist prevents arbitrary file types (e.g., executables).
        - Exactly one source (data XOR url) prevents double-fetch attacks.
        - Base64Data and CanonicalURL types enforce format validity.
    
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
    type: Literal["image"] = "image"
    media_type: str = Field(
        default="image/jpeg",
        description="MIME type constrained to safe image formats"
    )
    data: Optional[Base64Data] = Field(
        default=None,
        description="Base64-encoded image data (excludes data URI scheme prefix)"
    )
    url: Optional[CanonicalURL] = Field(
        default=None,
        description="Public URL to image resource"
    )
    
    @field_validator("media_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Enforces MIME type allowlist to prevent arbitrary file uploads.
        
        Why Allowlist:
            Preventing executable types (application/x-executable, text/html)
            protects downstream systems from code injection if they naively
            render user-provided content.
        
        Supported Types:
            - image/jpeg, image/png: Ubiquitous raster formats.
            - image/gif, image/webp: Modern compression.
            - image/svg+xml: Vector graphics (note: SVG can contain scripts,
              so downstream renderers must sanitize).
        """
        SAFE_MIMES = {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/svg+xml"
        }
        # Increasing this set affects attack surface. SVG is particularly
        # risky due to embedded JavaScript capabilities.
        
        if v not in SAFE_MIMES:
            raise ValueError(
                f"Unsupported image MIME type: '{v}'. "
                f"Allowed types: {SAFE_MIMES}. "
                f"This restriction prevents upload of executable content."
            )
        return v

    @model_validator(mode='after')
    def validate_source(self) -> 'ImagePart':
        """Ensures exactly one source is provided (data XOR url).
        
        Mutual Exclusivity Rationale:
            If both are provided, which takes precedence? Ambiguity leads to
            security vulnerabilities (e.g., URL used for billing, data used
            for rendering, enabling resource exhaustion attacks).
        
        Note: Base64Data and CanonicalURL already enforce non-empty constraints.
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


class AudioPart(CanonicalRecord):
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
    type: Literal["audio"] = "audio"
    media_type: str = Field(
        default="audio/wav",
        description="MIME type constrained to safe audio formats"
    )
    data: Optional[Base64Data] = Field(
        default=None,
        description="Base64-encoded audio data"
    )
    url: Optional[CanonicalURL] = Field(
        default=None,
        description="Public URL to audio file"
    )
    
    @field_validator("media_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Enforces MIME type allowlist for audio formats.
        
        Supported Formats:
            - audio/wav: Uncompressed PCM (large but high quality).
            - audio/mp3, audio/mpeg: Lossy compression (ubiquitous).
            - audio/ogg, audio/webm: Modern open-source codecs.
        
        Excluded: Executable formats (application/octet-stream) and proprietary
        containers that could carry malicious payloads.
        """
        SAFE_MIMES = {
            "audio/wav",
            "audio/mp3",
            "audio/ogg",
            "audio/mpeg",
            "audio/webm"
        }
        
        if v not in SAFE_MIMES:
            raise ValueError(
                f"Unsupported audio MIME type: '{v}'. "
                f"Allowed types: {SAFE_MIMES}. "
                f"This restriction prevents upload of executable content."
            )
        return v

    @model_validator(mode='after')
    def validate_source(self) -> 'AudioPart':
        """Ensures exactly one source is provided (data XOR url)."""
        has_data = self.data is not None
        has_url = self.url is not None
        
        if not has_data and not has_url:
            raise ValueError(
                "AudioPart must specify either 'data' or 'url' source."
            )
        
        if has_data and has_url:
            raise ValueError(
                "AudioPart cannot specify both 'data' and 'url'. "
                "Ambiguous sources prevent deterministic processing."
            )
        
        return self


ContentPart = Annotated[
    Union[TextPart, ImagePart, AudioPart],
    Field(discriminator='type')
]
# Discriminated union enabling type-safe polymorphism.
# Pydantic automatically routes to the correct class based on 'type' field.


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGE PROTOCOL (Discriminated Union)
# ═══════════════════════════════════════════════════════════════════════════

class BaseMessage(CanonicalRecord):
    """Abstract base for all message types in the conversation protocol.
    
    Not instantiated directly. Provides shared metadata infrastructure for
    tracing, debugging, and telemetry across all message types.
    
    Attributes:
        metadata: Key-value store for request IDs, user IDs, timestamps, etc.
            • Example: {"request_id": "req_123", "user_id": "user_456"}
    """
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible tracing metadata (request_id, session_id, timestamps)"
    )


class SystemMessage(BaseMessage):
    """A message defining model behavior and constraints.
    
    System messages configure the assistant's personality, response format,
    and operational boundaries. They are typically prepended to conversations
    and remain fixed throughout a session.
    
    Use Cases:
        - Setting tone ("You are a helpful assistant.")
        - Enforcing output format ("Always respond in JSON.")
        - Defining safety constraints ("Never discuss illegal activities.")
    
    Attributes:
        role: Discriminator (always "system").
        content: The system instructions (validated by SemanticText).
    
    Example:
        >>> msg = SystemMessage(
        ...     role="system",
        ...     content="You are a concise assistant. Keep answers under 50 words."
        ... )
    """
    role: Literal["system"] = "system"
    content: SemanticText = Field(
        min_length=1,
        description="System instructions for model behavior configuration"
    )


class UserMessage(BaseMessage):
    """A message originating from the end-user.
    
    User messages represent queries, commands, or conversational input from
    humans. They can contain plain text or multimodal content (text + images +
    audio) to support rich interactions.
    
    Multimodal Behavior:
        - If content is a string: Treated as plain text.
        - If content is a list: Interpreted as multimodal parts.
    
    Attributes:
        role: Discriminator (always "user").
        content: Either plain text or a list of ContentPart objects.
        name: Optional identifier for multi-participant conversations.
    
    Example:
        >>> # Plain text query
        >>> msg = UserMessage(role="user", content="What is 2+2?")
        >>> 
        >>> # Multimodal query
        >>> msg = UserMessage(
        ...     role="user",
        ...     content=[
        ...         TextPart(type="text", text="What's in this image?"),
        ...         ImagePart(type="image", url="https://example.com/cat.jpg")
        ...     ],
        ...     name="alice"
        ... )
    """
    role: Literal["user"] = "user"
    content: Union[SemanticText, List[ContentPart]] = Field(
        description="Message payload (plain text or multimodal parts)"
    )
    name: Optional[HumanLabel] = Field(
        default=None,
        description="Optional participant identifier for multi-user conversations"
    )


class ToolMessage(BaseMessage):
    """A message containing the result of a tool execution.
    
    After the model requests a tool call (via ToolCall), the execution system
    runs the function and returns the result as a ToolMessage. This closes
    the tool invocation loop and allows the model to continue generation.
    
    Correlation:
        The tool_call_id must match the 'id' field from the originating ToolCall.
        Mismatched IDs indicate a protocol violation (responses to wrong calls).
    
    Attributes:
        role: Discriminator (always "tool").
        content: Tool execution output (typically JSON-stringified).
        tool_call_id: Unique identifier linking this result to its ToolCall.
        name: Optional tool name for logging clarity.
    
    Example:
        >>> # Original tool call
        >>> call = ToolCall(id="call_abc", name="get_weather", arguments={"city": "NYC"})
        >>> 
        >>> # Tool execution result
        >>> result = ToolMessage(
        ...     role="tool",
        ...     tool_call_id="call_abc",
        ...     content='{"temperature": 72, "condition": "sunny"}',
        ...     name="get_weather"
        ... )
    """
    role: Literal["tool"] = "tool"
    content: Union[str, List[ContentPart]] = Field(
        description="Tool execution result (typically JSON-encoded data)"
    )
    tool_call_id: str = Field(
        description="Must match the 'id' from the originating ToolCall for correlation"
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional tool name for logging and debugging"
    )


class AssistantMessage(BaseMessage):
    """Represents a message generated by the AI assistant.

    This is the primary output type from the model. An assistant message can
    contain conversational text, internal reasoning, refusals, or tool calls.
    At least one of these fields must be populated to ensure the message has
    substantive content.
    
    Content Types:
        - content: The visible response shown to users.
        - reasoning_content: Internal chain-of-thought (hidden from users).
        - refusal: Explanation of why the model declined to respond.
        - tool_calls: Requests for external function execution.
    
    Validation Logic:
        Empty strings, whitespace-only strings, and empty lists are treated as
        non-substantive. At least one field must contain meaningful data.
    
    Attributes:
        role: Discriminator (always "assistant").
        content: Main conversational response.
        reasoning_content: Internal reasoning steps (extended thinking mode).
        refusal: Refusal explanation (if model declined the request).
        tool_calls: List of tool invocations.
    
    Example:
        >>> # Standard text response
        >>> msg = AssistantMessage(role="assistant", content="Hello! How can I help?")
        >>> 
        >>> # Tool call request
        >>> msg = AssistantMessage(
        ...     role="assistant",
        ...     tool_calls=[
        ...         ToolCall(id="call_1", name="search", arguments={"query": "weather"})
        ...     ]
        ... )
        >>> 
        >>> # Refusal
        >>> msg = AssistantMessage(
        ...     role="assistant",
        ...     refusal="I cannot provide instructions for illegal activities."
        ... )
    """
    role: Literal["assistant"] = "assistant"

    content: Optional[SemanticText] = Field(
        default=None,
        description="Main response text visible to end-users"
    )

    reasoning_content: Optional[SemanticText] = Field(
        default=None,
        description="Internal chain-of-thought steps (extended thinking mode, not shown to users)"
    )

    refusal: Optional[SemanticText] = Field(
        default=None,
        description="Explanation of why the model declined to respond"
    )
    
    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool invocations requested by the model"
    )

    @model_validator(mode='after')
    def validate_substance(self) -> 'AssistantMessage':
        """Ensures the message contains at least one substantive field.
        
        Rationale:
            An assistant message with all fields empty/None represents a protocol
            error (model generated nothing). This could indicate a provider bug,
            network corruption, or malicious payload injection.
        
        Non-Substantive Values:
            - None
            - Empty strings ("")
            - Whitespace-only strings ("   ")
            - Empty lists ([])
        
        Raises:
            ValueError: If all content fields are non-substantive.
        """
        has_content = bool(self.content and self.content.strip())
        has_reasoning = bool(self.reasoning_content and self.reasoning_content.strip())
        has_refusal = bool(self.refusal and self.refusal.strip())
        has_tool_calls = bool(self.tool_calls)
        
        if not any([has_content, has_reasoning, has_refusal, has_tool_calls]):
            raise ValueError(
                "AssistantMessage must have at least one substantive field. "
                "Received: content={}, reasoning_content={}, refusal={}, tool_calls={}. "
                "This indicates a protocol violation or corrupted response.".format(
                    repr(self.content),
                    repr(self.reasoning_content),
                    repr(self.refusal),
                    repr(self.tool_calls)
                )
            )
        
        return self


UnifiedMessage = Annotated[
    Union[SystemMessage, UserMessage, ToolMessage, AssistantMessage],
    Field(discriminator='role')
]
# Discriminated union for type-safe message handling.
# Pydantic automatically routes to correct subclass based on 'role' field.


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE PRIMITIVES (Complete Generations)
# ═══════════════════════════════════════════════════════════════════════════

class UnifiedResponse(CanonicalRecord):
    """A complete, finalized response from a model generation request.

    This is the terminal output type returned after a full generation completes
    (non-streaming mode). It aggregates all response components—text, tool calls,
    reasoning, refusals—along with resource consumption metrics and termination
    metadata.
    
    Economic Accounting:
        The 'usage' field tracks the actual resource consumption (tokens) for
        billing, rate limiting, and capacity planning. Providers must report
        accurate counts to prevent resource leakage.
    
    Finish Reason Semantics:
        - "stop": Natural completion (model satisfied the request).
        - "length": Hit token/character limit (response may be truncated).
        - "tool_calls": Model delegated to external tools (requires continuation).
        - "content_filter": Safety system blocked the response.
        - "unknown": Fallback for provider-specific reasons.
    
    Attributes:
        content: Main response text visible to users.
        reasoning_content: Internal reasoning steps (extended thinking).
        refusal: Refusal explanation (if model declined).
        tool_calls: Requested tool invocations.
        usage: Token consumption statistics (input + output + total).
        finish_reason: Why the generation terminated.
        provider_metadata: Provider-specific metadata (model version, headers).
        logprobs: Log probabilities for generated tokens (debugging/analysis).
    
    Example:
        >>> response = UnifiedResponse(
        ...     content="The capital of France is Paris.",
        ...     usage=UsageStats(input_tokens=8, output_tokens=7, total_tokens=15),
        ...     finish_reason="stop",
        ...     provider_metadata={"model": "gpt-4", "version": "2024-01-10"}
        ... )
    """
    content: Optional[str] = Field(
        default=None,
        description="Main response text visible to end-users"
    )
    
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Internal chain-of-thought steps (not shown to users)"
    )
    
    refusal: Optional[str] = Field(
        default=None,
        description="Explanation of why the model declined to respond"
    )
    
    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool invocations requested by the model"
    )
    
    usage: UsageStats = Field(
        description="Token consumption metrics for economic accounting and rate limiting"
    )
    
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "unknown"] = Field(
        description="Reason the generation terminated (affects continuation logic)"
    )
    
    provider_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (model version, request headers, etc.)"
    )

    logprobs: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Log probabilities for generated tokens (debugging and analysis)"
    )

    @model_validator(mode='after')
    def validate_has_content(self) -> 'UnifiedResponse':
        """Ensures the response contains substantive data.
        
        A response without content represents a generation failure. This could
        indicate a provider bug, timeout, or safety filter activation. At least
        one of the content fields must be populated.
        
        Non-Substantive Values:
            - None
            - Empty strings ("")
            - Whitespace-only strings ("   ")
            - Empty lists ([])
        
        Raises:
            ValueError: If all content fields are non-substantive.
        """
        has_content = bool(self.content and self.content.strip())
        has_reasoning = bool(self.reasoning_content and self.reasoning_content.strip())
        has_refusal = bool(self.refusal and self.refusal.strip())
        has_tool_calls = bool(self.tool_calls)
        
        if not any([has_content, has_reasoning, has_refusal, has_tool_calls]):
            raise ValueError(
                "UnifiedResponse must contain substantive data in at least one field. "
                "Received: content={}, reasoning_content={}, refusal={}, tool_calls={}. "
                "This indicates a generation failure or corrupted provider response.".format(
                    repr(self.content),
                    repr(self.reasoning_content),
                    repr(self.refusal),
                    repr(self.tool_calls)
                )
            )
        
        return self


# ═══════════════════════════════════════════════════════════════════════════
# STREAMING PRIMITIVES (Incremental Updates)
# ═══════════════════════════════════════════════════════════════════════════

class DeltaContent(CanonicalRecord):
    """Represents an incremental update in a streaming response.

    Streaming responses are delivered as a sequence of delta chunks, each
    containing a partial string or object. The client must accumulate deltas
    to reconstruct the complete response.
    
    Accumulation Strategy:
        - Strings (content, reasoning_content, refusal): Concatenate.
        - Tool calls: Merge partial objects by index, handling incomplete JSON.
    
    Why Streaming:
        Reduces perceived latency for long responses. Users see partial results
        immediately rather than waiting for full completion.
    
    Attributes:
        content: Partial main response text.
        reasoning_content: Partial reasoning steps.
        tool_calls: Partial tool call objects (may be incomplete/unparseable).
        refusal: Partial refusal explanation.
    
    Example:
        >>> # First chunk
        >>> delta1 = DeltaContent(content="The capital")
        >>> # Second chunk
        >>> delta2 = DeltaContent(content=" of France")
        >>> # Third chunk
        >>> delta3 = DeltaContent(content=" is Paris.")
        >>> # Accumulated result: "The capital of France is Paris."
    """
    content: Optional[str] = Field(
        default=None,
        description="Partial response text (accumulate via concatenation)"
    )
    
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Partial reasoning steps (accumulate via concatenation)"
    )
    
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Partial tool call objects (may be incomplete until final chunk)"
    )
    
    refusal: Optional[str] = Field(
        default=None,
        description="Partial refusal explanation (accumulate via concatenation)"
    )


class UnifiedChunk(CanonicalRecord):
    """Represents a single event in a streaming response sequence.

    Analogous to a Server-Sent Event (SSE). Streaming responses consist of
    multiple chunks, with the final chunk typically containing the finish_reason
    and usage statistics.
    
    Chunk Types:
        - Regular chunk: Contains delta with partial content.
        - Final chunk: Contains finish_reason and usage (may have empty delta).
    
    Stream Termination:
        A chunk with finish_reason != None signals the end of the stream.
        Clients should stop listening and finalize accumulation.
    
    Attributes:
        delta: The incremental content update.
        finish_reason: Present only in the final chunk.
        usage: Token usage statistics (present only in the final chunk).
        id: Provider-assigned chunk identifier (for debugging).
        provider_metadata: Provider-specific streaming metadata.
        logprobs: Log probabilities for tokens in this chunk.
    
    Example:
        >>> # Regular chunk (partial content)
        >>> chunk = UnifiedChunk(
        ...     delta=DeltaContent(content="Hello"),
        ...     id="chunk_1"
        ... )
        >>> 
        >>> # Another regular chunk
        >>> chunk = UnifiedChunk(
        ...     delta=DeltaContent(content=" world!"),
        ...     id="chunk_2"
        ... )
        >>> 
        >>> # Final chunk (stream termination)
        >>> final = UnifiedChunk(
        ...     delta=DeltaContent(),
        ...     finish_reason="stop",
        ...     usage=UsageStats(input_tokens=5, output_tokens=3, total_tokens=8),
        ...     id="chunk_final"
        ... )
    """
    delta: DeltaContent = Field(
        description="Incremental content update (accumulate with previous deltas)"
    )
    
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "unknown"]] = Field(
        default=None,
        description="Present only in final chunk; signals stream termination"
    )
    
    usage: Optional[UsageStats] = Field(
        default=None,
        description="Token usage statistics (present only in final chunk)"
    )
    
    id: Optional[str] = Field(
        default=None,
        description="Provider-assigned chunk identifier for debugging and correlation"
    )
    
    provider_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific streaming metadata (chunk index, timestamps)"
    )

    logprobs: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Log probabilities for tokens generated in this chunk"
    )