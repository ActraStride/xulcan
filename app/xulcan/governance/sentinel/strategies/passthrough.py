"""Passthrough Sentinel — approves everything. Default for development."""

from __future__ import annotations

from xulcan.governance.sentinel.base import (
    BaseSentinelStrategy, BaseSentinelConfig,
    SentinelResult, SentinelVerdict
)
from xulcan.protocol.tools import ToolCall


class PassthroughSentinelConfig(BaseSentinelConfig):
    """No parameters. Passthrough approves all tool calls."""
    pass


class PassthroughSentinelStrategy(BaseSentinelStrategy):
    """Always approves. Equivalent to a structural stub.

    Use for:
        - Development and testing.
        - Fully trusted agents in controlled environments.
        - When no policy enforcement is needed.

    YAML:
        sentinel_strategy: "passthrough"
        sentinel_params: {}
    """

    ConfigSchema = PassthroughSentinelConfig

    def _check(self, call: ToolCall) -> SentinelResult:
        return SentinelResult(verdict=SentinelVerdict.APPROVED)