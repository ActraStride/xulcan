"""
Conversation protocol and message types for model interactions.

This module defines the structured message format that forms the conversation
history between users, models, and tools. It implements a discriminated union
pattern for type-safe message handling and enforces strict validation rules
to prevent protocol violations.

Message Types:
    - SystemMessage: Defines model behavior and constraints
    - UserMessage: End-user input (text or multimodal)
    - ToolMessage: Tool execution results
    - AssistantMessage: Model-generated responses

Security Features:
    - Discriminated unions prevent type confusion attacks.
    - Substantive content validation rejects empty messages.
    - Metadata extensibility for tracing and telemetry.

Type Aliases:
    UnifiedMessage: Discriminated union of all message types

Enums:
    Role: Defines valid message roles in a conversation
"""

from __future__ import annotations

from typing import Literal, Annotated
from enum import Enum

from pydantic import Field, model_validator, field_validator

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    SemanticText,
    DisplayName,
    ExternalID,
    JsonDict
)

from .parts import ContentPart
from .tools import ToolCall


# =============================================================================
# DOMAIN ENUMERATIONS
# =============================================================================

class Role(str, Enum):
    """Defines valid message roles in a conversation.

    These roles enforce the protocol contract between user, system, assistant,
    and tool execution layers. Not exported publicly to prevent external misuse.

    Attributes:
        SYSTEM: Configuration message for model behavior.
        USER: End-user input message.
        ASSISTANT: Model-generated response.
        TOOL: Result of a tool execution.
    """
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# =============================================================================
# MESSAGE PROTOCOL (Discriminated Union)
# =============================================================================

class BaseMessage(ImmutableRecord):
    """Abstract base for all message types in the conversation protocol.

    Not instantiated directly. Provides shared metadata infrastructure for
    tracing, debugging, and telemetry across all message types.

    Attributes:
        metadata: Key-value store for request IDs, user IDs, timestamps, etc.
            Example: {"request_id": "req_123", "user_id": "user_456"}
    """
    metadata: JsonDict = Field(
        default_factory=dict,
        description="Extensible tracing metadata (request_id, session_id, timestamps)."
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
    role: Literal[Role.SYSTEM] = Role.SYSTEM
    content: SemanticText = Field(
        min_length=1,
        description="System instructions for model behavior configuration."
    )

    @field_validator("content", mode="after")
    @classmethod
    def validate_content_substance(cls, value: str) -> str:
        """Enforces system instructions are not empty/whitespace.

        Args:
            value: The content string to validate.

        Returns:
            The validated content string.

        Raises:
            ValueError: If the content is empty or whitespace-only.
        """
        if not value.strip():
            raise ValueError("System message content cannot be empty or whitespace-only.")
        return value


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
    role: Literal[Role.USER] = Role.USER
    content: SemanticText | list[ContentPart] = Field(
        description="Message payload (plain text or multimodal parts)."
    )
    name: DisplayName | None = Field(
        default=None,
        description="Optional participant identifier for multi-user conversations."
    )

    @field_validator("content", mode="after")
    @classmethod
    def validate_content_substance(cls, value: str | list[ContentPart]) -> str | list[ContentPart]:
        """Enforces that content is not empty, not whitespace-only, and strictly typed.

        Args:
            value: The content to validate (string or list of ContentPart).

        Returns:
            The validated content.

        Raises:
            ValueError: If content is empty, whitespace-only (for strings),
                        or an empty list.
        """
        if isinstance(value, list) and not value:
            raise ValueError("Content list cannot be empty.")

        if isinstance(value, str) and not value.strip():
            raise ValueError("Content cannot be empty or whitespace-only.")

        return value


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
    role: Literal[Role.TOOL] = Role.TOOL
    content: SemanticText | list[ContentPart] = Field(
        description="Tool execution result (typically JSON-encoded data)."
    )
    tool_call_id: ExternalID = Field(
        description="Must match the 'id' from the originating ToolCall for correlation."
    )
    name: MachineID | None = Field(
        default=None,
        description="Optional tool name for logging and debugging."
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
    role: Literal[Role.ASSISTANT] = Role.ASSISTANT

    content: SemanticText | None = Field(
        default=None,
        description="Main response text visible to end-users."
    )

    reasoning_content: SemanticText | None = Field(
        default=None,
        description="Internal chain-of-thought steps (extended thinking mode, not shown to users)."
    )

    refusal: SemanticText | None = Field(
        default=None,
        description="Explanation of why the model declined to respond."
    )

    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Tool invocations requested by the model."
    )

    @model_validator(mode='after')
    def validate_substance(self) -> AssistantMessage:
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

        Returns:
            AssistantMessage: The validated instance.

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


# =============================================================================
# TYPE ALIASES
# =============================================================================

# Discriminated union for type-safe message handling.
# Pydantic automatically routes to the correct subclass based on 'role' field.
UnifiedMessage = Annotated[
    SystemMessage | UserMessage | ToolMessage | AssistantMessage,
    Field(discriminator='role')
]
