"""Unit Tests for xulcan.protocol.messages module.

Test Suite Coverage:
    - Class 1: BaseMessage metadata infrastructure
    - Class 2: SystemMessage constraint validation
    - Class 3: UserMessage polymorphic content handling
    - Class 4: ToolMessage correlation integrity
    - Class 5: AssistantMessage substantive content validation (CRITICAL)
    - Class 6: UnifiedMessage discriminated union routing

Philosophy: Protocol Integrity, Type Safety, Zero-Tolerance for Empty Messages.
"""

import pytest
import json
from typing import Any, Dict, List
from pydantic import ValidationError, TypeAdapter

from xulcan.protocol.message import (
    BaseMessage,
    SystemMessage,
    UserMessage,
    ToolMessage,
    AssistantMessage,
    UnifiedMessage,
    Role,
)
from xulcan.protocol.parts import TextPart, ImagePart, ContentPart
from xulcan.protocol.tools import ToolCall


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 1: BASE MESSAGE INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestBaseMessageInfrastructure:
    """Validates inherited metadata behavior and tracing support."""

    def test_metadata_default_initialization(self, valid_system_message: SystemMessage) -> None:
        """Should initialize with empty metadata dictionary by default."""
        assert valid_system_message.metadata == {}
        assert isinstance(valid_system_message.metadata, dict)

    def test_metadata_custom_initialization(self, mock_provider_metadata: Dict[str, Any]) -> None:
        """Should accept custom metadata during construction."""
        custom_meta = {
            "request_id": "req_123",
            "user_id": "user_456",
            "session_id": "sess_789"
        }
        
        msg = SystemMessage(
            role="system",
            content="Test",
            metadata=custom_meta
        )
        
        assert msg.metadata == custom_meta
        assert msg.metadata["request_id"] == "req_123"

    def test_metadata_isolation(self) -> None:
        """Should maintain metadata isolation between message instances."""
        msg1 = SystemMessage(role="system", content="First", metadata={"key": "value1"})
        msg2 = SystemMessage(role="system", content="Second", metadata={"key": "value2"})
        
        msg1.metadata["key"] = "modified"
        
        # msg2 should remain unchanged
        assert msg2.metadata["key"] == "value2"

    def test_metadata_serialization(self, valid_user_message_text: UserMessage) -> None:
        """Should serialize metadata with primitive types to JSON."""
        metadata = {
            "request_id": "req_123",
            "retry_count": 3,
            "tags": ["production", "urgent"],
            "config": {"timeout": 30, "enabled": True}
        }
        
        msg = UserMessage(
            role="user", 
            content=valid_user_message_text.content, 
            metadata=metadata
        )
        
        # Serialize and verify
        json_str = msg.model_dump_json()
        reconstructed = json.loads(json_str)
        
        assert reconstructed["metadata"] == metadata


class TestRoleEnum:
    """Validates Role enum values for protocol compliance."""

    def test_enum_values_match_protocol(self) -> None:
        """Should have exact string values matching conversation protocol."""
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"

    def test_enum_members_are_strings(self) -> None:
        """Should be string enum for JSON serialization."""
        for role in Role:
            assert isinstance(role.value, str)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 2: SYSTEM MESSAGE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestSystemMessage:
    """Validates system instruction constraints and immutability."""

    def test_role_literal_lock(self) -> None:
        """Should only accept 'system' as role value."""
        with pytest.raises(ValidationError):
            SystemMessage(
                role="user",  # type: ignore
                content="Invalid role"
            )

    def test_construct_valid(self, valid_system_message: SystemMessage) -> None:
        """Should create valid system message with instructions."""
        assert valid_system_message.role == "system"
        assert isinstance(valid_system_message.content, str)
        assert len(valid_system_message.content) > 0

    def test_content_min_length_enforcement(self) -> None:
        """Should reject empty content string."""
        with pytest.raises(ValidationError) as exc:
            SystemMessage(role="system", content="")
        
        assert "at least 1 character" in str(exc.value).lower() or "min_length" in str(exc.value).lower()

    def test_content_whitespace_rejection(self) -> None:
        """Should reject whitespace-only content."""
        with pytest.raises(ValidationError):
            SystemMessage(role="system", content="   ")

    def test_accepts_multiline_instructions(self) -> None:
        """Should accept multiline system instructions."""
        multiline = """You are a helpful assistant.
Follow these rules:
1. Be concise
2. Be accurate
3. Be respectful"""
        
        msg = SystemMessage(role="system", content=multiline)
        assert "\n" in msg.content

    def test_serialization_format(self, valid_system_message: SystemMessage) -> None:
        """Should serialize to expected protocol format."""
        serialized = valid_system_message.model_dump()
        
        assert serialized["role"] == "system"
        assert isinstance(serialized["content"], str)
        assert "metadata" in serialized


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 3: USER MESSAGE POLYMORPHIC HANDLING
# ═══════════════════════════════════════════════════════════════════════════

class TestUserMessageTextContent:
    """Validates plain text user message handling."""

    def test_role_literal_lock(self) -> None:
        """Should only accept 'user' as role value."""
        with pytest.raises(ValidationError):
            UserMessage(
                role="assistant",  # type: ignore
                content="Invalid role"
            )

    def test_content_str_handling(self, valid_user_message_text: UserMessage) -> None:
        """Should accept and preserve plain text content."""
        assert valid_user_message_text.role == "user"
        assert isinstance(valid_user_message_text.content, str)
        assert len(valid_user_message_text.content) > 0

    def test_content_minimum_length(self) -> None:
        """Should reject empty string content."""
        with pytest.raises(ValidationError):
            UserMessage(role="user", content="")

    def test_name_field_optional(self, valid_user_message_text: UserMessage) -> None:
        """Should allow name field to be None."""
        assert valid_user_message_text.name is None

    def test_name_field_valid(self, valid_user_message_text: UserMessage) -> None:
        """Should accept valid participant name."""
        msg = UserMessage(
            role="user",
            content=valid_user_message_text.content,
            name="alice"
        )
        assert msg.name == "alice"


class TestUserMessageMultimodalContent:
    """Validates multimodal content part handling."""

    def test_content_multimodal_list(
        self, 
        valid_text_part: TextPart, 
        valid_image_part_url: ImagePart
    ) -> None:
        """Should accept list of ContentPart objects."""
        msg = UserMessage(
            role="user",
            content=[valid_text_part, valid_image_part_url]
        )
        
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextPart)
        assert isinstance(msg.content[1], ImagePart)

    def test_content_single_part_list(self, valid_text_part: TextPart) -> None:
        """Should accept list with single content part."""
        msg = UserMessage(
            role="user",
            content=[valid_text_part]
        )
        
        assert isinstance(msg.content, list)
        assert len(msg.content) == 1

    def test_content_empty_list_rejection(self) -> None:
        """Should reject empty content list."""
        with pytest.raises(ValidationError):
            UserMessage(role="user", content=[])

    def test_multimodal_with_name(self, valid_text_part: TextPart) -> None:
        """Should accept multimodal content with participant name."""
        msg = UserMessage(
            role="user",
            content=[valid_text_part],
            name="bob"
        )
        
        assert msg.name == "bob"
        assert isinstance(msg.content, list)

    def test_serialization_preserves_content_type(
        self, 
        valid_text_part: TextPart, 
        valid_image_part_url: ImagePart
    ) -> None:
        """Should maintain content structure through serialization."""
        msg = UserMessage(
            role="user",
            content=[valid_text_part, valid_image_part_url]
        )
        
        serialized = msg.model_dump()
        
        assert isinstance(serialized["content"], list)
        assert len(serialized["content"]) == 2
        assert serialized["content"][0]["type"] == "text"
        assert serialized["content"][1]["type"] == "image"


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 4: TOOL MESSAGE CORRELATION
# ═══════════════════════════════════════════════════════════════════════════

class TestToolMessage:
    """Validates tool execution result correlation integrity."""

    def test_role_literal_lock(self, valid_tool_id: str) -> None:
        """Should only accept 'tool' as role value."""
        with pytest.raises(ValidationError):
            ToolMessage(
                role="user",  # type: ignore
                content="Result",
                tool_call_id=valid_tool_id
            )

    def test_tool_call_id_mandatory(self) -> None:
        """Should require tool_call_id for correlation."""
        with pytest.raises(ValidationError):
            ToolMessage(
                role="tool",
                content="Result data"
                # Missing tool_call_id
            )

    def test_construct_valid(self, valid_tool_message: ToolMessage) -> None:
        """Should create valid tool message with correlation ID."""
        assert valid_tool_message.role == "tool"
        assert valid_tool_message.tool_call_id is not None
        assert isinstance(valid_tool_message.content, str)

    def test_content_is_payload(self, valid_tool_id: str) -> None:
        """Should accept JSON-stringified content as payload."""
        json_payload = json.dumps({"status": "success", "data": [1, 2, 3]})
        
        msg = ToolMessage(
            role="tool",
            content=json_payload,
            tool_call_id=valid_tool_id
        )
        
        # Verify it's stored as string
        assert isinstance(msg.content, str)
        # Verify it can be parsed back
        parsed = json.loads(msg.content)
        assert parsed["status"] == "success"

    def test_name_field_optional(self, valid_tool_message: ToolMessage) -> None:
        """Should allow optional tool name for logging."""
        # Check if the fixture has a name or create one without
        msg = ToolMessage(
            role="tool",
            content=valid_tool_message.content,
            tool_call_id=valid_tool_message.tool_call_id
        )
        
        # Name can be None or have a value
        assert msg.name is None or isinstance(msg.name, str)

    def test_name_field_present(self, valid_tool_id: str) -> None:
        """Should accept tool name when provided."""
        msg = ToolMessage(
            role="tool",
            content="Weather data",
            tool_call_id=valid_tool_id,
            name="get_weather"
        )
        
        assert msg.name == "get_weather"

    def test_correlation_with_tool_call(self, valid_tool_call: ToolCall) -> None:
        """Should correlate with originating ToolCall via matching IDs."""
        # Original tool call
        call_id = valid_tool_call.id
        
        # Tool execution result
        result = ToolMessage(
            role="tool",
            content='{"result": "success"}',
            tool_call_id=call_id,
            name=valid_tool_call.name
        )
        
        assert result.tool_call_id == call_id


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 5: ASSISTANT MESSAGE SUBSTANTIVE VALIDATION (CRITICAL)
# ═══════════════════════════════════════════════════════════════════════════

class TestAssistantMessageSubstanceValidation:
    """Validates critical validate_substance logic - prevents empty responses."""

    def test_role_literal_lock(self) -> None:
        """Should only accept 'assistant' as role value."""
        with pytest.raises(ValidationError):
            AssistantMessage(
                role="user",  # type: ignore
                content="Invalid"
            )

    def test_substance_all_empty_fails(self) -> None:
        """Should raise ValidationError if all content fields are None/empty."""
        with pytest.raises(ValidationError) as exc:
            AssistantMessage(
                role="assistant",
                content=None,
                reasoning_content=None,
                refusal=None,
                tool_calls=None
            )
        
        assert "substantive" in str(exc.value).lower() or "protocol violation" in str(exc.value).lower()

    def test_substance_whitespace_content_fails(self) -> None:
        """Should raise ValidationError if content is only whitespace."""
        with pytest.raises(ValidationError) as exc:
            AssistantMessage(
                role="assistant",
                content="   ",
                reasoning_content=None,
                refusal=None,
                tool_calls=None
            )
        
        assert "substantive" in str(exc.value).lower()

    def test_substance_empty_string_fails(self) -> None:
        """Should raise ValidationError if content is empty string."""
        with pytest.raises(ValidationError):
            AssistantMessage(
                role="assistant",
                content=""
            )

    def test_substance_empty_tool_calls_fails(self) -> None:
        """Should raise ValidationError if tool_calls is empty list."""
        with pytest.raises(ValidationError):
            AssistantMessage(
                role="assistant",
                content=None,
                tool_calls=[]
            )


class TestAssistantMessageValidCombinations:
    """Validates all acceptable combinations of substantive content."""

    def test_substance_content_only_succeeds(
        self, 
        valid_assistant_message_content: AssistantMessage
    ) -> None:
        """Should accept message with only content field."""
        assert valid_assistant_message_content.content is not None
        assert valid_assistant_message_content.tool_calls is None
        assert valid_assistant_message_content.refusal is None

    def test_substance_tool_calls_only_succeeds(
        self, 
        valid_assistant_message_tool_call: AssistantMessage
    ) -> None:
        """Should accept message with only tool_calls field."""
        assert valid_assistant_message_tool_call.content is None
        assert valid_assistant_message_tool_call.tool_calls is not None
        assert len(valid_assistant_message_tool_call.tool_calls) == 1

    def test_substance_refusal_only_succeeds(self) -> None:
        """Should accept message with only refusal field."""
        msg = AssistantMessage(
            role="assistant",
            refusal="I cannot provide instructions for illegal activities."
        )
        
        assert msg.refusal is not None
        assert msg.content is None
        assert msg.tool_calls is None

    def test_substance_reasoning_only_succeeds(self) -> None:
        """Should accept message with only reasoning_content field."""
        msg = AssistantMessage(
            role="assistant",
            reasoning_content="Let me think through this step by step..."
        )
        
        assert msg.reasoning_content is not None
        assert msg.content is None

    def test_substance_content_and_tool_calls_succeeds(
        self, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept message with both content and tool_calls."""
        msg = AssistantMessage(
            role="assistant",
            content="Let me check the weather for you.",
            tool_calls=[valid_tool_call]
        )
        
        assert msg.content is not None
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1

    def test_substance_refusal_and_tool_calls_succeeds(
        self, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept refusal with tool_calls (edge case)."""
        msg = AssistantMessage(
            role="assistant",
            refusal="I cannot fulfill part X, but here's a tool for Y.",
            tool_calls=[valid_tool_call]
        )
        
        assert msg.refusal is not None
        assert msg.tool_calls is not None

    def test_substance_all_fields_populated_succeeds(
        self, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept message with all fields populated."""
        msg = AssistantMessage(
            role="assistant",
            content="Response text",
            reasoning_content="Internal thoughts",
            refusal=None,  # Not all fields required
            tool_calls=[valid_tool_call]
        )
        
        assert msg.content is not None
        assert msg.reasoning_content is not None
        assert msg.tool_calls is not None


class TestAssistantMessageReasoningContent:
    """Validates reasoning_content (chain-of-thought) isolation."""

    def test_reasoning_content_storage(self) -> None:
        """Should store reasoning_content separately from main content."""
        msg = AssistantMessage(
            role="assistant",
            content="The answer is 4.",
            reasoning_content="First, I need to add 2+2, which equals 4."
        )
        
        assert msg.content == "The answer is 4."
        assert msg.reasoning_content == "First, I need to add 2+2, which equals 4."

    def test_reasoning_without_content_succeeds(self) -> None:
        """Should allow reasoning_content alone as substantive."""
        msg = AssistantMessage(
            role="assistant",
            reasoning_content="Analyzing the problem... Step 1: ..."
        )
        
        assert msg.reasoning_content is not None
        assert msg.content is None

    def test_serialization_includes_reasoning(self) -> None:
        """Should serialize reasoning_content field."""
        msg = AssistantMessage(
            role="assistant",
            content="Answer",
            reasoning_content="Thinking steps"
        )
        
        serialized = msg.model_dump()
        
        assert "reasoning_content" in serialized
        assert serialized["reasoning_content"] == "Thinking steps"


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 6: UNIFIED MESSAGE POLYMORPHISM
# ═══════════════════════════════════════════════════════════════════════════

class TestUnifiedMessageDiscriminator:
    """Validates discriminated union routing via 'role' field."""

    def test_discriminator_routing_system(
        self, 
        valid_system_message: SystemMessage
    ) -> None:
        """Should resolve to SystemMessage when role='system'."""
        payload = {"role": "system", "content": valid_system_message.content}
        adapter = TypeAdapter(UnifiedMessage)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, SystemMessage)
        assert result.role == "system"

    def test_discriminator_routing_user(
        self, 
        valid_user_message_text: UserMessage
    ) -> None:
        """Should resolve to UserMessage when role='user'."""
        payload = {"role": "user", "content": valid_user_message_text.content}
        adapter = TypeAdapter(UnifiedMessage)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, UserMessage)
        assert result.role == "user"

    def test_discriminator_routing_assistant(
        self, 
        valid_assistant_message_content: AssistantMessage
    ) -> None:
        """Should resolve to AssistantMessage when role='assistant'."""
        payload = {"role": "assistant", "content": valid_assistant_message_content.content}
        adapter = TypeAdapter(UnifiedMessage)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, AssistantMessage)
        assert result.role == "assistant"

    def test_discriminator_routing_tool(self, valid_tool_id: str) -> None:
        """Should resolve to ToolMessage when role='tool'."""
        payload = {
            "role": "tool",
            "content": "Result data",
            "tool_call_id": valid_tool_id
        }
        adapter = TypeAdapter(UnifiedMessage)
        
        result = adapter.validate_python(payload)
        
        assert isinstance(result, ToolMessage)
        assert result.role == "tool"

    def test_unknown_role_rejection(self) -> None:
        """Should raise ValidationError for unknown role."""
        payload = {"role": "hacker", "content": "Malicious"}
        adapter = TypeAdapter(UnifiedMessage)
        
        with pytest.raises(ValidationError) as exc:
            adapter.validate_python(payload)
        
        assert "hacker" in str(exc.value).lower() or "discriminator" in str(exc.value).lower()

    def test_missing_discriminator(self) -> None:
        """Should raise ValidationError if role field is missing."""
        payload = {"content": "No role specified"}
        adapter = TypeAdapter(UnifiedMessage)
        
        with pytest.raises(ValidationError) as exc:
            adapter.validate_python(payload)
        
        assert "discriminator" in str(exc.value).lower() or "role" in str(exc.value).lower()


class TestUnifiedMessageRoundtrip:
    """Validates JSON serialization integrity across message types."""

    def test_roundtrip_system_message(
        self, 
        valid_system_message: SystemMessage
    ) -> None:
        """Should maintain integrity through JSON roundtrip for SystemMessage."""
        original = SystemMessage(
            role="system",
            content=valid_system_message.content,
            metadata={"version": "1.0"}
        )
        
        json_str = original.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(UnifiedMessage)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, SystemMessage)
        assert reconstructed.content == original.content
        assert reconstructed.metadata == original.metadata

    def test_roundtrip_user_message_text(
        self, 
        valid_user_message_text: UserMessage
    ) -> None:
        """Should maintain integrity for UserMessage with text content."""
        original = UserMessage(
            role="user",
            content=valid_user_message_text.content,
            name="alice"
        )
        
        json_str = original.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(UnifiedMessage)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, UserMessage)
        assert reconstructed.content == original.content
        assert reconstructed.name == original.name

    def test_roundtrip_assistant_message_with_tools(
        self, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should maintain integrity for AssistantMessage with tool_calls."""
        original = AssistantMessage(
            role="assistant",
            content="Searching...",
            tool_calls=[valid_tool_call]
        )
        
        json_str = original.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(UnifiedMessage)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, AssistantMessage)
        assert reconstructed.content == original.content
        assert len(reconstructed.tool_calls) == 1

    def test_roundtrip_tool_message(self, valid_tool_id: str) -> None:
        """Should maintain integrity for ToolMessage."""
        original = ToolMessage(
            role="tool",
            content='{"result": "success"}',
            tool_call_id=valid_tool_id,
            name="search_api"
        )
        
        json_str = original.model_dump_json()
        reconstructed_dict = json.loads(json_str)
        
        adapter = TypeAdapter(UnifiedMessage)
        reconstructed = adapter.validate_python(reconstructed_dict)
        
        assert isinstance(reconstructed, ToolMessage)
        assert reconstructed.tool_call_id == original.tool_call_id
        assert reconstructed.name == original.name


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES AND PROTOCOL VIOLATIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestProtocolViolations:
    """Validates detection of protocol violations and corrupted messages."""

    def test_assistant_with_all_whitespace_fields(self) -> None:
        """Should detect all-whitespace as non-substantive."""
        with pytest.raises(ValidationError):
            AssistantMessage(
                role="assistant",
                content="   ",
                reasoning_content="  ",
                refusal="    "
            )

    @pytest.mark.parametrize("invalid_content", [
        12345,
        True,
        [],
        {},
    ])
    def test_user_message_type_coercion_prevention(self, invalid_content: Any) -> None:
        """Should not coerce non-string types to string."""
        with pytest.raises(ValidationError):
            UserMessage(
                role="user",
                content=invalid_content  # type: ignore
            )

    def test_tool_message_empty_correlation_id(self) -> None:
        """Should reject empty tool_call_id."""
        with pytest.raises(ValidationError):
            ToolMessage(
                role="tool",
                content="Result",
                tool_call_id=""
            )

    def test_metadata_accepts_nested_structures(
        self, 
        valid_system_message: SystemMessage
    ) -> None:
        """Should accept complex nested metadata structures."""
        complex_metadata = {
            "trace": {
                "span_id": "span_123",
                "parent_id": "parent_456",
                "attributes": {
                    "environment": "production",
                    "version": "2.0"
                }
            },
            "metrics": [
                {"name": "latency", "value": 150},
                {"name": "tokens", "value": 500}
            ]
        }
        
        msg = SystemMessage(
            role="system",
            content=valid_system_message.content,
            metadata=complex_metadata
        )
        
        assert msg.metadata["trace"]["span_id"] == "span_123"
        assert len(msg.metadata["metrics"]) == 2