"""Protocol dimension: Messages, parts, tools, and IO for model communication."""

from .parts import ContentPart, TextPart, ImagePart, AudioPart, ContentType
from .tools import ToolCall, FunctionDef, ToolDefinition, NamedToolChoice, ToolChoice, ToolChoiceType
from .message import UnifiedMessage, SystemMessage, UserMessage, AssistantMessage, ToolMessage, Role
from .io import UnifiedResponse, DeltaContent, UnifiedChunk, FinishReason

__all__ =[
    # Parts
    "ContentPart", "TextPart", "ImagePart", "AudioPart", "ContentType",
    # Tools
    "ToolCall", "FunctionDef", "ToolDefinition", "NamedToolChoice", "ToolChoice", "ToolChoiceType",
    # Messages
    "UnifiedMessage", "SystemMessage", "UserMessage", "AssistantMessage", "ToolMessage", "Role",
    # IO / Responses
    "UnifiedResponse", "DeltaContent", "UnifiedChunk", "FinishReason"
]