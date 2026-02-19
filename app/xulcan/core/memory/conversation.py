"""Conversation management for orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


@dataclass
class Message:
    role: str
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationManager:
    """Manages conversation history and context."""

    def __init__(self, max_messages: int = 50) -> None:
        self.max_messages = max_messages
        self.messages: List[Message] = []
        self.context: Dict[str, Any] = {}

    def add_message(
        self, role: str, content: Any, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        message = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(message)

        if len(self.messages) > self.max_messages:
            system_messages = [msg for msg in self.messages if msg.role == "system"]
            other_messages = [msg for msg in self.messages if msg.role != "system"]
            keep_count = self.max_messages - len(system_messages)
            self.messages = system_messages + other_messages[-keep_count:]

    def get_messages(self) -> List[Dict[str, Any]]:
        return [
            {"role": msg.role, "content": msg.content, **({"metadata": msg.metadata} if msg.metadata else {})}
            for msg in self.messages
        ]

    def add_tool_result(self, tool_name: str, result: Any, success: bool = True) -> None:
        content = f"Tool '{tool_name}' executed successfully: {result}"
        if not success:
            content = f"Tool '{tool_name}' failed: {result}"
        self.add_message(
            role="tool",
            content=content,
            metadata={"tool_name": tool_name, "success": success, "result": result},
        )

    def set_context(self, key: str, value: Any) -> None:
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def clear_context(self) -> None:
        self.context.clear()

    def clear(self) -> None:
        self.messages.clear()
        self.context.clear()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_messages": len(self.messages),
            "user_messages": len([m for m in self.messages if m.role == "user"]),
            "assistant_messages": len([m for m in self.messages if m.role == "assistant"]),
            "tool_messages": len([m for m in self.messages if m.role == "tool"]),
            "context_keys": list(self.context.keys()),
            "oldest_message": self.messages[0].timestamp if self.messages else None,
            "newest_message": self.messages[-1].timestamp if self.messages else None,
        }
