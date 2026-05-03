"""Blocklist Sentinel — blocks specific tool names and dangerous argument patterns.

Two layers of defense:
    1. Tool name blocklist  — certain tools are never permitted.
    2. Argument pattern blocklist — certain argument values trigger escalation
       (e.g., 'rm -rf', 'DROP TABLE', shell injection patterns).
"""

from __future__ import annotations

from typing import Any
from pydantic import Field, field_validator

from xulcan.core import MachineID

from xulcan.governance.sentinel.base import (
    BaseSentinelStrategy, BaseSentinelConfig,
    SentinelResult, SentinelVerdict
)
from xulcan.protocol.tools import ToolCall


class BlocklistSentinelConfig(BaseSentinelConfig):
    """Configuration for the Blocklist Sentinel.

    Attributes:
        blocked_tools:      Tool names that are unconditionally rejected.
        dangerous_patterns: Substrings in any argument value that trigger ESCALATE.
                            These don't outright block — they ask a human first.

    Example YAML:
        sentinel_strategy: "blocklist"
        sentinel_params:
          blocked_tools:
            - "sandbox_run_bash"   # Never allow bash in this agent
          dangerous_patterns:
            - "rm -rf"
            - "DROP TABLE"
            - "DROP DATABASE"
            - "; rm "
            - "| bash"
    """
    blocked_tools: set[MachineID] = Field(
        default_factory=set,
        description="Tool names that are unconditionally rejected."
    )
    
    dangerous_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Substrings that, if found in any argument value, trigger ESCALATE "
            "instead of APPROVED. Human must approve before execution."
        )
    )

    @field_validator("dangerous_patterns", mode="after")
    @classmethod
    def lower_patterns(cls, patterns: list[str]) -> list[str]:
        """Pre-computes lowercase patterns for faster evaluation."""
        return[p.lower() for p in patterns]


class BlocklistSentinelStrategy(BaseSentinelStrategy):
    """Enforces a blocklist of tool names and dangerous argument patterns.

    Evaluation order:
        1. If tool name is in blocked_tools → BLOCKED (hard rejection).
        2. If any argument value contains a dangerous_pattern → ESCALATE.
        3. Otherwise → APPROVED.

    Use for:
        - Production agents with known dangerous tools.
        - Agents that handle user input that could contain injection attacks.
        - Multi-tenant systems where different agents have different permissions.
    """

    ConfigSchema = BlocklistSentinelConfig

    def _check(self, call: ToolCall) -> SentinelResult:
        # 1. Tool name hard block (O(1) lookup since blocked_tools is a set)
        if call.name in self.config.blocked_tools:
            return SentinelResult(
                verdict=SentinelVerdict.BLOCKED,
                reason=(
                    f"Tool '{call.name}' is in the blocklist and cannot be executed. "
                    f"Blocked tools: {list(self.config.blocked_tools)}"
                )
            )

        # 2. Dangerous argument pattern → escalate to human
        if self.config.dangerous_patterns:
            for arg_name, arg_value in call.arguments.items():
                for pattern in self.config.dangerous_patterns:
                    if self._contains_pattern(arg_value, pattern):
                        return SentinelResult(
                            verdict=SentinelVerdict.ESCALATE,
                            reason=(
                                f"Argument '{arg_name}' in tool '{call.name}' contains "
                                f"the dangerous pattern '{pattern}'. "
                                f"Human approval required before execution."
                            )
                        )

        return SentinelResult(verdict=SentinelVerdict.APPROVED)

    def _contains_pattern(self, data: Any, pattern: str) -> bool:
        """Recursively search for a substring pattern inside nested JSON payloads.
        
        This prevents bypasses where the LLM hides a dangerous payload 
        deep inside a list or a nested dictionary object.
        """
        if isinstance(data, str):
            return pattern in data.lower()
        elif isinstance(data, dict):
            return any(self._contains_pattern(v, pattern) for v in data.values())
        elif isinstance(data, list) or isinstance(data, tuple):
            return any(self._contains_pattern(item, pattern) for item in data)
        return False