"""Sliding Window Context Strategy.

Maintains only the N most recent messages, discarding older ones,
while ensuring the resulting sequence remains valid for LLM consumption.
"""

from __future__ import annotations

import logging
from pydantic import Field

from xulcan.context.base import BaseContextStrategy, BaseContextConfig
from xulcan.protocol.message import UnifiedMessage, AssistantMessage

logger = logging.getLogger("xulcan.context.sliding_window")


class SlidingWindowConfig(BaseContextConfig):
    """Parameters for the SlidingWindow strategy."""
    max_messages: int = Field(
        default=10,
        gt=0,
        description="Maximum number of messages to keep (most recent N messages)."
    )


class SlidingWindowStrategy(BaseContextStrategy):
    """Keeps only the N most recent messages, discarding older ones.

    Guarantees a valid message sequence after cutting.
    General orphan cleanup is inherited from BaseContextStrategy.build_prompt(),
    but this strategy handles boundary issues created specifically by the cut.

    Sequence repair mechanisms:
        1. Boundary Orphan Cleanup: If the cut splits a ToolCall request from 
           its result, the partial exchange is removed.
        2. Anchor Repair: If the cut leaves an AssistantMessage(tool_calls) 
           as the very first message, the window expands backward until a valid 
           anchor (e.g., a UserMessage) is found to provide context.

    YAML:
        context_strategy: "sliding_window"
        context_params:
          max_messages: 8
    """

    ConfigSchema = SlidingWindowConfig

    async def _apply_strategy(
        self,
        messages: list[UnifiedMessage]
    ) -> list[UnifiedMessage]:
        
        limit = self.config.max_messages

        # Step 1: Basic cut
        if len(messages) <= limit:
            return messages
            
        cut = messages[-limit:]

        # Step 2: Remove orphans created by the cut FIRST.
        # Although the base class cleans orphans from the full history,
        # our arbitrary slice [-limit:] might have cut right in the middle
        # of a tool exchange. We must clean these boundary orphans.
        cut = self._remove_orphaned_tool_calls(cut)

        # Step 3: Repair leading sequence on the already-cleaned result.
        # We must do this AFTER orphan removal, otherwise the repair might
        # anchor on a message that gets removed, bringing us back to square one.
        cut = self._repair_leading_sequence(cut, messages)

        return cut

    def _repair_leading_sequence(
        self,
        cut: list[UnifiedMessage],
        original: list[UnifiedMessage],
    ) -> list[UnifiedMessage]:
        """Ensure the first message is a valid anchor for the LLM.

        A valid anchor is any message that is NOT an AssistantMessage with
        tool_calls. An LLM starting a context window mid-tool-execution 
        without the preceding prompt often hallucinates or rejects the request.
        
        If we cut mid-exchange, we expand the window backward into the 
        original history until we find a stable starting point.
        """
        if not cut:
            return cut

        first = cut[0]
        
        # If the first message isn't an Assistant trying to execute a tool, it's a valid anchor.
        if not (isinstance(first, AssistantMessage) and first.tool_calls):
            return cut

        try:
            # We locate the exact instance in the original array.
            # Works perfectly because Pydantic models evaluate equality by values.
            idx = original.index(first)
        except ValueError:
            logger.warning(
                "🔧 [SlidingWindow] First message is an invalid AssistantMessage "
                "but was not found in original history. Dropping it to prevent errors."
            )
            return cut[1:]

        anchor_idx = idx
        while anchor_idx > 0:
            anchor_idx -= 1
            candidate = original[anchor_idx]
            
            # Found a message that is NOT a tool-calling Assistant message
            if not (isinstance(candidate, AssistantMessage) and candidate.tool_calls):
                logger.debug(
                    f"🔧 [SlidingWindow] Expanded window backward by "
                    f"{idx - anchor_idx} message(s) to repair sequence anchor."
                )
                # Return from original to guarantee we bring back valid sequences
                return original[anchor_idx:]

        logger.debug("🔧 [SlidingWindow] Could not find anchor, returning full history.")
        return original