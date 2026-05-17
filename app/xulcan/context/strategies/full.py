"""Full History Context Strategy.

Returns the complete conversation history without any truncation.
"""

from __future__ import annotations

from xulcan.context.base import BaseContextStrategy, BaseContextConfig
from xulcan.protocol.message import UnifiedMessage


class FullHistoryConfig(BaseContextConfig):
    """No parameters needed — returns 100% of history."""
    pass


class FullHistoryStrategy(BaseContextStrategy):
    """Returns the complete conversation history without any truncation.

    Use for:
        - Short conversations where token overflow is not a concern.
        - Agents that need full context (psychoanalysts, summarizers, auditors).
        - Default strategy when no specific strategy is declared.

    YAML:
        context_strategy: "full_history"
        context_params: {}
    """

    ConfigSchema = FullHistoryConfig

    async def _apply_strategy(
        self,
        messages: list[UnifiedMessage]
    ) -> list[UnifiedMessage]:
        """Returns the messages unmodified."""
        return messages