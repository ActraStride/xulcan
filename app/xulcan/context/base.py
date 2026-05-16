"""Base configuration and template methods for Context Strategies.

This module defines the abstract foundation for Context Engines. It ensures
that cross-cutting concerns (like Jinja2 template rendering, StateStore
injection, and message history sanitization) are applied uniformly before
any specific context truncation algorithm (like Sliding Window) is executed.

NOTE: BaseContextConfig has been moved to xulcan.core.contracts to enable
imports from the blueprint layer without pulling in the full context engine
machinery (ABC, UnifiedMessage protocol, Jinja2 rendering, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from xulcan.core import MachineID
from xulcan.contracts import BaseContextConfig  # ← Importado desde contracts
from xulcan.protocol.message import UnifiedMessage, SystemMessage, AssistantMessage, ToolMessage
from xulcan.utils.template import render_template

if TYPE_CHECKING:
    from xulcan.blueprint.schema import AgentBlueprint
    from xulcan.kernel.environment import SystemEnvironment


class BaseContextStrategy(ABC):
    """Abstract base class for all Context Engines.

    Deliberately does NOT inherit ContextStrategy (Protocol).
    Duck typing handles structural compatibility.

    Template Method pattern:
        build_prompt() handles the cross-cutting concerns (Jinja2, SystemMessage placement).
        _apply_strategy() is the pure algorithm each subclass implements.
    """

    ConfigSchema: type[BaseContextConfig] = BaseContextConfig

    def __init__(self, config: BaseContextConfig):
        self.config = config

    async def build_prompt(
        self,
        messages: list[UnifiedMessage],
        blueprint: AgentBlueprint,
        run_id: MachineID,
        environment: SystemEnvironment | None = None
    ) -> list[UnifiedMessage]:
        """Template method — do not override. Override _apply_strategy instead.

        Steps:
            1. Render system_prompt with Jinja2 + StateStore memory.
            2. Strip stale SystemMessages from history (prevents duplicates).
            3. Remove orphaned tool call pairs (governance blocks create these).
            4. Apply the strategy algorithm (_apply_strategy).
            5. Prepend the fresh rendered SystemMessage at index 0.
        """
        # 1. RENDER SYSTEM PROMPT (Jinja2 + StateStore)
        rendered_prompt = blueprint.system_prompt
        if environment and environment.state_store:
            memory_dict = await environment.resolve_memory(run_id)
            rendered_prompt = render_template(blueprint.system_prompt, memory_dict)

        # 2. STRIP STALE SYSTEM MESSAGES
        clean_messages = [m for m in messages if not isinstance(m, SystemMessage)]

        # 3. REMOVE ORPHANED TOOL CALL PAIRS
        # Governance blocks/rejects pop AssistantMessages from context but the
        # Ledger still stored them. Hydration replays create orphaned pairs.
        # All strategies need this cleanup — it lives here so none can skip it.
        clean_messages = self._remove_orphaned_tool_calls(clean_messages)

        # 4. APPLY STRATEGY (subclass decides what to keep)
        processed_messages = await self._apply_strategy(clean_messages)

        # 5. ASSEMBLE: fresh SystemMessage is always index 0
        return [SystemMessage(content=rendered_prompt)] + processed_messages

    def _remove_orphaned_tool_calls(
        self,
        messages: list[UnifiedMessage]
    ) -> list[UnifiedMessage]:
        """Remove incomplete tool call exchanges from the message sequence.

        An exchange is only valid if an AssistantMessage requests N tools,
        and there are exactly N ToolMessages fulfilling those requests.

        Two types of orphans can exist after a context cut or governance block:
        Type A: AssistantMessage without all corresponding ToolMessages.
        Type B: ToolMessage without a corresponding AssistantMessage request.

        Both types are removed strictly to prevent LLM Provider API HTTP 400 errors.
        """
        declared_ids = set()   # tool_call_ids declared in AssistantMessages
        responded_ids = set()  # tool_call_ids that have a ToolMessage response

        # 1. Map all declarations and responses
        for msg in messages:
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    declared_ids.add(tc.id)
            elif isinstance(msg, ToolMessage):
                responded_ids.add(msg.tool_call_id)

        # 2. Identify fully satisfied AssistantMessages
        # An AssistantMessage is ONLY valid if ALL its tool calls have responses.
        valid_call_ids = set()
        for msg in messages:
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                call_ids = {tc.id for tc in msg.tool_calls}
                if call_ids.issubset(responded_ids):
                    valid_call_ids.update(call_ids)

        # 3. Filter the message list
        clean_messages = []
        for msg in messages:
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                # Keep only if ALL requested tools were successfully responded to
                call_ids = {tc.id for tc in msg.tool_calls}
                if call_ids.issubset(valid_call_ids):
                    clean_messages.append(msg)
            elif isinstance(msg, ToolMessage):
                # Keep only if its original request is also being kept
                if msg.tool_call_id in valid_call_ids:
                    clean_messages.append(msg)
            else:
                # Keep System and User messages unconditionally
                clean_messages.append(msg)

        return clean_messages

    @abstractmethod
    async def _apply_strategy(
        self,
        messages: list[UnifiedMessage]
    ) -> list[UnifiedMessage]:
        """Pure algorithmic logic. Receives clean messages, returns filtered messages.

        No I/O, no Jinja2, no database calls — just list manipulation.
        """
        pass
