"""Defines standardized types for model interactions, including messages,
responses, tool calls, and multimodal content.

This module provides a set of Pydantic models that create a unified,
provider-agnostic interface for interacting with various generative models.
It includes robust and type-safe definitions for messages, content parts
(text, image, audio), tool usage, and streaming responses.
"""

from typing import Any, Dict, List, Literal, Optional, Union, Annotated
from pydantic import Field, model_validator
from enum import Enum

from .base import CanonicalModel, UsageStats


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL ENUMS (Not exported in __init__.py)
# ═══════════════════════════════════════════════════════════════════════════

class _Role(str, Enum):
    """Internal enum for message role validation.
    
    External APIs use string literals ("system", "user", etc.) for stability.
    This enum is used internally for validation and provider mapping only.
    """
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class _FinishReason(str, Enum):
    """Internal enum for finish reason validation.
    
    External APIs use string literals for stability. This enum is used
    internally for validation and provider mapping only.
    """
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    UNKNOWN = "unknown"


class _ContentType(str, Enum):
    """Internal enum for content type validation."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class _ToolChoiceType(str, Enum):
    """Internal enum for tool choice mode validation."""
    AUTO = "auto"
    NONE = "none"
    REQUIRED = "required"
    FUNCTION = "function"


# ═══════════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

class ToolCall(CanonicalModel):
    """Represents a model's request to execute an external tool.
    
    Attributes:
        id: Unique identifier for this tool call (provider-generated).
        name: The name of the function/tool to execute.
        arguments: Parsed JSON arguments as a dictionary.
    
    Example:
        >>> call = ToolCall(
        ...     id="call_abc123",
        ...     name="web_search",
        ...     arguments={"query": "weather in Paris"}
        ... )
    """
    id: str = Field(description="Unique identifier for this tool call")
    name: str = Field(description="Name of the function to execute")
    arguments: Dict[str, Any] = Field(
        description="Parsed JSON arguments for the function"
    )


class FunctionDef(CanonicalModel):
    """Defines a function that a model can invoke.
    
    This follows the OpenAI function calling schema format for compatibility.
    
    Attributes:
        name: Function name (must be valid identifier).
        description: Human-readable description of what the function does.
        parameters: JSON Schema object describing the function parameters.
    
    Example:
        >>> func = FunctionDef(
        ...     name="get_weather",
        ...     description="Get current weather for a location",
        ...     parameters={
        ...         "type": "object",
        ...         "properties": {
        ...             "location": {"type": "string"}
        ...         },
        ...         "required": ["location"]
        ...     }
        ... )
    """
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(
        description="JSON Schema defining the function parameters"
    )


class ToolDefinition(CanonicalModel):
    """Provides a structured definition for a tool, such as a function.
    
    Currently only supports function-type tools, but designed to be
    extensible for other tool types in the future.
    """
    type: Literal["function"] = "function"
    function: FunctionDef


class NamedToolChoice(CanonicalModel):
    """Specifies a particular function that the model must call.
    
    Used when you want to force the model to call a specific function.
    
    Example:
        >>> choice = NamedToolChoice(
        ...     type="function",
        ...     function={"name": "get_weather"}
        ... )
    """
    type: Literal["function"] = "function"
    function: Dict[str, str] = Field(
        description="Must contain 'name' key with the function name"
    )


# Union type for tool choice: either a mode string or a specific function
ToolChoice = Union[_ToolChoiceType, NamedToolChoice]


# ═══════════════════════════════════════════════════════════════════════════
# MULTIMODAL CONTENT PARTS
# ═══════════════════════════════════════════════════════════════════════════

class TextPart(CanonicalModel):
    """A content part containing plain text.
    
    Example:
        >>> part = TextPart(type="text", text="Hello, world!")
    """
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, description="The text content")


class ImagePart(CanonicalModel):
    """A content part representing an image.
    
    Must provide either base64-encoded data OR a URL, but not both.
    
    Attributes:
        type: Discriminator field (always "image").
        media_type: MIME type (e.g., "image/jpeg", "image/png").
        data: Base64-encoded image data (without data URI prefix).
        url: Public URL to the image.
    
    Example:
        >>> # From URL
        >>> img = ImagePart(
        ...     type="image",
        ...     url="https://example.com/image.jpg"
        ... )
        >>> # From base64
        >>> img = ImagePart(
        ...     type="image",
        ...     data="iVBORw0KGgoAAAANS..."
        ... )
    """
    type: Literal["image"] = "image"
    media_type: str = Field(
        default="image/jpeg",
        description="MIME type of the image"
    )
    data: Optional[str] = Field(
        default=None,
        description="Base64-encoded image data"
    )
    url: Optional[str] = Field(
        default=None,
        description="Public URL to the image"
    )

    @model_validator(mode='after')
    def validate_source(self) -> 'ImagePart':
        """Ensure that either 'data' or 'url' is provided, but not both."""
        has_data = bool(self.data and self.data.strip())
        has_url = bool(self.url and self.url.strip())
        
        if not has_data and not has_url:
            raise ValueError("ImagePart must have either 'data' or 'url'")
        
        if has_data and has_url:
            raise ValueError("ImagePart cannot have both 'data' and 'url'")
        
        return self


class AudioPart(CanonicalModel):
    """A content part representing an audio clip.
    
    Must provide either base64-encoded data OR a URL, but not both.
    
    Attributes:
        type: Discriminator field (always "audio").
        media_type: MIME type (e.g., "audio/wav", "audio/mp3").
        data: Base64-encoded audio data.
        url: Public URL to the audio file.
    """
    type: Literal["audio"] = "audio"
    media_type: str = Field(
        default="audio/wav",
        description="MIME type of the audio"
    )
    data: Optional[str] = Field(
        default=None,
        description="Base64-encoded audio data"
    )
    url: Optional[str] = Field(
        default=None,
        description="Public URL to the audio file"
    )

    @model_validator(mode='after')
    def validate_source(self) -> 'AudioPart':
        """Ensure that either 'data' or 'url' is provided, but not both."""
        has_data = bool(self.data and self.data.strip())
        has_url = bool(self.url and self.url.strip())
        
        if not has_data and not has_url:
            raise ValueError("AudioPart must have either 'data' or 'url'")
        
        if has_data and has_url:
            raise ValueError("AudioPart cannot have both 'data' and 'url'")
        
        return self


# Discriminated union for content parts
ContentPart = Annotated[
    Union[TextPart, ImagePart, AudioPart],
    Field(discriminator='type')
]


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGE TYPES (Discriminated Union)
# ═══════════════════════════════════════════════════════════════════════════

class BaseMessage(CanonicalModel):
    """Base class defining shared properties for all message types.
    
    Not instantiated directly; use concrete message types.
    """
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tracing metadata (request_id, user_id, timestamps, etc.)"
    )


class SystemMessage(BaseMessage):
    """A message providing instructions or context to the model.
    
    Used to set the behavior, personality, or constraints of the assistant.
    
    Example:
        >>> msg = SystemMessage(
        ...     role="system",
        ...     content="You are a helpful assistant that speaks like a pirate."
        ... )
    """
    role: Literal["system"] = "system"
    content: str = Field(min_length=1, description="System instructions")


class UserMessage(BaseMessage):
    """A message originating from the end-user.
    
    Can contain plain text or multimodal content (text + images + audio).
    
    Attributes:
        role: Always "user".
        content: Either a string or a list of content parts.
        name: Optional user identifier for multi-user conversations.
    
    Example:
        >>> # Text only
        >>> msg = UserMessage(role="user", content="What's the weather?")
        >>> 
        >>> # Multimodal
        >>> msg = UserMessage(
        ...     role="user",
        ...     content=[
        ...         TextPart(type="text", text="What's in this image?"),
        ...         ImagePart(type="image", url="https://example.com/img.jpg")
        ...     ]
        ... )
    """
    role: Literal["user"] = "user"
    content: Union[str, List[ContentPart]] = Field(
        description="Message content (text or multimodal)"
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional name/ID of the user"
    )


class ToolMessage(BaseMessage):
    """A message containing the result of a tool execution.
    
    Sent back to the model after executing a tool call.
    
    Attributes:
        role: Always "tool".
        content: The tool's output (typically JSON-stringified).
        tool_call_id: Must match the id from the original ToolCall.
        name: Optional tool name for clarity.
    
    Example:
        >>> msg = ToolMessage(
        ...     role="tool",
        ...     tool_call_id="call_abc123",
        ...     content='{"temperature": 72, "condition": "sunny"}'
        ... )
    """
    role: Literal["tool"] = "tool"
    content: str = Field(description="Tool execution result")
    tool_call_id: str = Field(
        description="Must match the id from the ToolCall that triggered this"
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional tool name"
    )


class AssistantMessage(BaseMessage):
    """Represents a message from the assistant (model).

    Can contain text, tool calls, refusals, or internal reasoning.
    Must have at least one substantive field populated.
    
    Attributes:
        role: Always "assistant".
        content: The main response text shown to users.
        reasoning_content: Internal chain-of-thought (not shown to users).
        refusal: Explanation of why the model refused to answer.
        tool_calls: List of tool invocations the model wants to make.
    
    Example:
        >>> # Text response
        >>> msg = AssistantMessage(role="assistant", content="Hello!")
        >>> 
        >>> # Tool call
        >>> msg = AssistantMessage(
        ...     role="assistant",
        ...     tool_calls=[
        ...         ToolCall(id="1", name="search", arguments={"q": "weather"})
        ...     ]
        ... )
        >>> 
        >>> # Refusal
        >>> msg = AssistantMessage(
        ...     role="assistant",
        ...     refusal="I cannot help with that request."
        ... )
    """
    role: Literal["assistant"] = "assistant"
    
    content: Optional[str] = Field(
        default=None,
        description="Main response text visible to users"
    )
    
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Internal reasoning/chain-of-thought steps (extended thinking)"
    )
    
    refusal: Optional[str] = Field(
        default=None,
        description="Explanation if the model refused to respond"
    )
    
    tool_calls: Optional[List[ToolCall]] = Field(
        default=None,
        description="Tool invocations requested by the model"
    )

    @model_validator(mode='after')
    def validate_substance(self) -> 'AssistantMessage':
        """Ensure the message contains at least one substantive field.
        
        Empty strings, whitespace-only strings, and empty lists are
        considered non-substantive.
        
        Raises:
            ValueError: If all fields are empty/None.
        """
        has_content = bool(self.content and self.content.strip())
        has_reasoning = bool(self.reasoning_content and self.reasoning_content.strip())
        has_refusal = bool(self.refusal and self.refusal.strip())
        has_tool_calls = bool(self.tool_calls)  # Empty list is falsy
        
        if not any([has_content, has_reasoning, has_refusal, has_tool_calls]):
            raise ValueError(
                "AssistantMessage must have at least one substantive field: "
                "content, reasoning_content, refusal, or tool_calls"
            )
        
        return self


# Discriminated union for all message types
UnifiedMessage = Annotated[
    Union[SystemMessage, UserMessage, ToolMessage, AssistantMessage],
    Field(discriminator='role')
]


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE TYPES (Static)
# ═══════════════════════════════════════════════════════════════════════════

class UnifiedResponse(CanonicalModel):
    """A standardized, complete response from a model generation request.

    This is the primary output type returned by LLM providers after
    completing a generation request.
    
    Attributes:
        content: Main response text.
        reasoning_content: Internal reasoning steps (if supported).
        refusal: Refusal message (if model declined to respond).
        tool_calls: Requested tool invocations.
        usage: Token usage statistics.
        finish_reason: Why the generation stopped.
        provider_metadata: Provider-specific metadata (model version, etc.).
    
    Example:
        >>> response = UnifiedResponse(
        ...     content="The weather is sunny.",
        ...     usage=UsageStats(input_tokens=10, output_tokens=5, total_tokens=15),
        ...     finish_reason="stop"
        ... )
    """
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    refusal: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    
    usage: UsageStats = Field(
        description="Token usage statistics for this generation"
    )
    
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "unknown"] = Field(
        description="Reason the generation terminated"
    )
    
    provider_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (model version, headers, etc.)"
    )

    @model_validator(mode='after')
    def validate_has_content(self) -> 'UnifiedResponse':
        """Ensure the response contains substantive data.
        
        At least one of content, reasoning_content, refusal, or tool_calls
        must be populated.
        
        Raises:
            ValueError: If all content fields are empty.
        """
        has_content = bool(self.content and self.content.strip())
        has_reasoning = bool(self.reasoning_content and self.reasoning_content.strip())
        has_refusal = bool(self.refusal and self.refusal.strip())
        has_tool_calls = bool(self.tool_calls)
        
        if not any([has_content, has_reasoning, has_refusal, has_tool_calls]):
            raise ValueError(
                "UnifiedResponse must contain substantive data in at least one field: "
                "content, reasoning_content, refusal, or tool_calls"
            )
        
        return self


# ═══════════════════════════════════════════════════════════════════════════
# STREAMING TYPES (Chunks)
# ═══════════════════════════════════════════════════════════════════════════

class DeltaContent(CanonicalModel):
    """Represents an incremental update within a streaming response.

    Each field contains a partial string or object that, when accumulated
    with previous deltas, constructs the final response.
    
    Example:
        >>> # First chunk
        >>> delta1 = DeltaContent(content="Hello")
        >>> # Second chunk
        >>> delta2 = DeltaContent(content=" world")
        >>> # Combined: "Hello world"
    """
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Partial tool call objects (may be incomplete)"
    )
    refusal: Optional[str] = None


class UnifiedChunk(CanonicalModel):
    """Represents a single event in a streaming response sequence.

    Analogous to a Server-Sent Event (SSE). The final chunk in a stream
    typically includes the finish_reason and final usage statistics.
    
    Attributes:
        delta: The incremental content update.
        finish_reason: Present only in the final chunk.
        usage: Token usage (present only in the final chunk).
        id: Optional chunk identifier from the provider.
        provider_metadata: Provider-specific streaming metadata.
    
    Example:
        >>> # Regular chunk
        >>> chunk = UnifiedChunk(
        ...     delta=DeltaContent(content="Hello"),
        ...     id="chunk_1"
        ... )
        >>> 
        >>> # Final chunk
        >>> final = UnifiedChunk(
        ...     delta=DeltaContent(content=""),
        ...     finish_reason="stop",
        ...     usage=UsageStats(input_tokens=10, output_tokens=5, total_tokens=15)
        ... )
    """
    delta: DeltaContent
    
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "unknown"]] = None
    
    usage: Optional[UsageStats] = None
    
    id: Optional[str] = Field(
        default=None,
        description="Provider-assigned chunk ID"
    )
    
    provider_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific streaming metadata"
    )