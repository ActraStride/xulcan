# app/xulcan/core/types/__init__.py
"""
Public API for Xulcan's type system.

This module exposes only the concrete types that external consumers
(API clients, agent definitions, etc.) should use. Internal enums and
helpers remain private to ensure API stability.
"""

# ═══════════════════════════════════════════════════════════════════════════
# 1. BASE MODELS
# ═══════════════════════════════════════════════════════════════════════════
from .base import (
    CanonicalRecord,
    MAX_IDENTIFIER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_SEMANTIC_TEXT_LENGTH,
    CanonicalIdentifier,
    HumanLabel,
    SemanticText,
    CanonicalURL,
    Base64Data,
    UsageStats,
    BudgetConfig,
    BudgetStrategy,
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. PROTOCOL (LLM Wire Format)
# ═══════════════════════════════════════════════════════════════════════════
from .protocol import (
    # Base Types
    Role,
    FinishReason,
    ContentType,
    ToolChoiceType,

    # Discriminated Union Types (these are what users actually use)
    UnifiedMessage,      # Union[SystemMessage | UserMessage | ToolMessage | AssistantMessage]
    ContentPart,         # Union[TextPart | ImagePart | AudioPart]
    
    # Concrete Message Types
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
    
    # Content Part Types
    TextPart,
    ImagePart,
    AudioPart,
    
    # Tool-related Types
    ToolCall,
    ToolChoice,
    NamedToolChoice,
    ToolDefinition,
    FunctionDef,
    
    # Response Types
    UnifiedResponse,
    UnifiedChunk,
    DeltaContent,
    
    # ❌ REMOVED: Role, FinishReason (internal enums)
    # Users should only interact with string literals in JSON/Pydantic models
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. BLUEPRINT (Agent Configuration)
# ═══════════════════════════════════════════════════════════════════════════
from .blueprint import (
    AgentBlueprint,
    AgentToolConfig,
    # ❌ REMOVED: ModelProvider (internal enum)
    # Users specify provider as string: "openai", "anthropic", "google"
)

# ═══════════════════════════════════════════════════════════════════════════
# 4. EVENTS (Runtime Execution History)
# ═══════════════════════════════════════════════════════════════════════════
from .events import (
    RunEvent,
    # ❌ REMOVED: RunStatus, EventType (internal enums)
    # The API returns these as strings in the event payload
)

# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API SURFACE
# ═══════════════════════════════════════════════════════════════════════════
__all__ = [
    # Base
    "CanonicalRecord",
    "MAX_IDENTIFIER_LENGTH",
    "MAX_LABEL_LENGTH",
    "MAX_SEMANTIC_TEXT_LENGTH",
    "CanonicalIdentifier",
    "HumanLabel",
    "SemanticText",
    "CanonicalURL",
    "Base64Data",
    "UsageStats",
    "BudgetConfig",
    "BudgetStrategy",

    # Protocol - Messages
    "Role",
    "FinishReason",
    "ContentType",
    "ToolChoiceType",
    "UnifiedMessage",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    
    # Protocol - Content
    "ContentPart",
    "TextPart",
    "ImagePart",
    "AudioPart",
    
    # Protocol - Tools
    "ToolCall",
    "ToolChoice",
    "NamedToolChoice",
    "ToolDefinition",
    "FunctionDef",
    
    # Protocol - Responses
    "UnifiedResponse",
    "UnifiedChunk",
    "DeltaContent",
    
    # Blueprint
    "AgentBlueprint",
    "AgentToolConfig",
    
    # Events
    "RunEvent",
]

# ═══════════════════════════════════════════════════════════════════════════
# USAGE EXAMPLES (for documentation)
# ═══════════════════════════════════════════════════════════════════════════
"""
CORRECT USAGE:
--------------
from xulcan.core.types import SystemMessage, UnifiedMessage

# ✅ Users work with concrete types and strings
msg = SystemMessage(role="system", content="You are a helpful assistant")

# ✅ Type checkers understand discriminated unions
messages: list[UnifiedMessage] = [
    SystemMessage(role="system", content="..."),
    UserMessage(role="user", content="Hello"),
]

# ✅ JSON serialization uses string literals
msg.model_dump()
# {"role": "system", "content": "...", "metadata": {}}


INTERNAL USAGE (in core/llm/):
-------------------------------
from xulcan.core.types.protocol import Role, FinishReason  # Private import

# ✅ Enums OK for internal validation/mapping
if message.role == "system":  # Compare to literal
    internal_role = Role.SYSTEM  # Convert to enum for provider adapter
"""