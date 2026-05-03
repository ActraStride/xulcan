"""Level 1 Fixtures: Protocol Definitions.

Fixtures for Tools, Messages, Parts, and I/O.
Inherits Level 0 fixtures (UsageStats, MachineID, etc.) automatically from ../conftest.py
"""

import pytest
from typing import Dict, Any, List

# Imports directos de las definiciones del Protocolo
from xulcan.protocol.tools import (
    ToolCall, 
    FunctionDef, 
    ToolDefinition
)
from xulcan.protocol.parts import (
    TextPart, 
    ImagePart
)
from xulcan.protocol.message import (
    SystemMessage, 
    UserMessage, 
    AssistantMessage, 
    ToolMessage
)
from xulcan.protocol.io import (
    UnifiedResponse, 
    UnifiedChunk, 
    DeltaContent,
    ToolCallDelta,
    FunctionCallDelta,
    FinishReason
)

# ═══════════════════════════════════════════════════════════════════════════
# TOOLS & FUNCTIONS (Capabilities)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_tool_id() -> str:
    """Standard ID for tool calls to avoid hardcoding strings in tests."""
    return "call_abc123"

@pytest.fixture
def valid_tool_call_args() -> Dict[str, Any]:
    """Safe, serializable arguments for a tool call (Dictionary format)."""
    return {"location": "San Francisco", "unit": "celsius"}

@pytest.fixture
def valid_tool_call(valid_tool_id, valid_machine_id, valid_tool_call_args) -> ToolCall:
    """A fully hydrated ToolCall object using Core fixtures."""
    return ToolCall(
        id=valid_tool_id,
        name=valid_machine_id,
        arguments=valid_tool_call_args
    )

@pytest.fixture
def valid_function_def(valid_machine_id) -> FunctionDef:
    """A valid function definition with JSON Schema parameters."""
    return FunctionDef(
        name=valid_machine_id,
        description="Retrieves weather data.",
        parameters={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location"]
        }
    )

@pytest.fixture
def valid_tool_definition(valid_function_def) -> ToolDefinition:
    """A ToolDefinition wrapper (as sent to the LLM API)."""
    return ToolDefinition(
        type="function",
        function=valid_function_def
    )

# ═══════════════════════════════════════════════════════════════════════════
# PARTS (Content Blocks)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_text_part() -> TextPart:
    """Standard text content part."""
    return TextPart(text="Hello from Xulcan.")

@pytest.fixture
def valid_image_part_url(valid_safe_url) -> ImagePart:
    """Image part referencing an external URL."""
    return ImagePart(
        url={"url": valid_safe_url},
        media_type="image/png"
    )

@pytest.fixture
def valid_image_part_base64(valid_base64_data) -> ImagePart:
    """Image part containing inline base64 data."""
    return ImagePart(
        data={"url": f"data:image/png;base64,{valid_base64_data}"},
        media_type="image/png"
    )

# ═══════════════════════════════════════════════════════════════════════════
# MESSAGES (The Conversation)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_system_message() -> SystemMessage:
    """Immutable system instruction."""
    return SystemMessage(
        content="You are a strict, type-safe assistant.",
        role="system"
    )

@pytest.fixture
def valid_user_message_text() -> UserMessage:
    """Simple text-only user message."""
    return UserMessage(
        content="What is the weather in SF?",
        role="user"
    )

@pytest.fixture
def valid_user_message_multimodal(valid_text_part, valid_image_part_url) -> UserMessage:
    """Complex multimodal user message (Text + Image)."""
    return UserMessage(
        content=[valid_text_part, valid_image_part_url],
        role="user"
    )

@pytest.fixture
def valid_assistant_message_content() -> AssistantMessage:
    """Standard assistant response with text."""
    return AssistantMessage(
        content="The weather is sunny.",
        role="assistant"
    )

@pytest.fixture
def valid_assistant_message_tool_call(valid_tool_call) -> AssistantMessage:
    """Assistant response invoking a tool (no text content)."""
    return AssistantMessage(
        tool_calls=[valid_tool_call],
        role="assistant"
    )

@pytest.fixture
def valid_tool_message(valid_tool_id) -> ToolMessage:
    """Result of a tool execution."""
    return ToolMessage(
        tool_call_id=valid_tool_id,
        content='{"temperature": 22}',
        role="tool",
        name="get_weather"
    )

# ═══════════════════════════════════════════════════════════════════════════
# IO & STREAMING (Kernel Output)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_provider_metadata() -> Dict[str, Any]:
    """Safe metadata dictionary mimicking a provider response."""
    return {
        "model": "gpt-4-turbo",
        "system_fingerprint": "fp_12345",
        "cached": False
    }

@pytest.fixture
def valid_unified_response(
    valid_assistant_message_content, 
    valid_usage_stats, 
    mock_provider_metadata
) -> UnifiedResponse:
    """Complete, finalized response from the Kernel."""
    return UnifiedResponse(
        content=valid_assistant_message_content.content,
        usage=valid_usage_stats,
        finish_reason=FinishReason.STOP,
        provider_metadata=mock_provider_metadata
    )

@pytest.fixture
def valid_tool_call_delta(valid_machine_id) -> ToolCallDelta:
    """Partial tool call for streaming tests."""
    return ToolCallDelta(
        index=0,
        type="function",
        function=FunctionCallDelta(
            name=valid_machine_id,
            arguments='{"location": "San' # Partial JSON string
        )
    )

@pytest.fixture
def valid_unified_chunk_delta(valid_tool_call_delta) -> UnifiedChunk:
    """Streaming chunk containing a partial update."""
    return UnifiedChunk(
        delta=DeltaContent(
            content="Hello",
            tool_calls=[valid_tool_call_delta]
        ),
        id="chunk_1"
    )