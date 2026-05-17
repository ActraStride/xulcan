"""Terminal HumanGate — blocks execution and waits for operator input via stdin.

This is the simplest real human-in-the-loop implementation.
Suitable for local development, CLI bots, and operator-supervised agents.

For production (web APIs, async workers), use WebhookHumanGate instead —
blocking stdin in an async context is not suitable for server deployments.
"""

from __future__ import annotations

import asyncio
import json
from pydantic import Field

from xulcan.core import MachineID
from xulcan.governance.human.base import (
    BaseHumanGateStrategy, BaseHumanGateConfig,
    HumanGateResult, HumanGateDecision
)
from xulcan.protocol.tools import ToolCall


class TerminalHumanGateConfig(BaseHumanGateConfig):
    """Configuration for the Terminal HumanGate.

    Attributes:
        show_arguments: Whether to display the full tool arguments to the operator.
                        Disable for sensitive data (API keys, PII in args).
        timeout_seconds: Seconds to wait for operator input before auto-rejecting.
                         0 means wait forever.
    """
    show_arguments: bool = Field(
        default=True,
        description="Display tool arguments to the operator before asking for approval."
    )
    
    timeout_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Seconds to wait before auto-rejecting. 0.0 = wait forever."
    )


class TerminalHumanGateStrategy(BaseHumanGateStrategy):
    """Blocks execution and prompts the operator for approval via stdin.

    Displays the tool call details and reason, then waits for y/n input.
    Optionally times out and auto-rejects if the operator doesn't respond.

    Use for:
        - CLI bots and terminal interfaces (like your hacker bot).
        - Local development with human supervision.
        - Demos where you want visible approval gates.

    YAML:
        human_gate_strategy: "terminal"
        human_gate_params:
          show_arguments: true
          timeout_seconds: 60
    """

    ConfigSchema = TerminalHumanGateConfig

    async def _obtain_decision(
        self,
        call: ToolCall,
        reason: str,
        run_id: MachineID,
    ) -> HumanGateResult:

        # Build the approval prompt
        print("\n" + "═" * 60)
        print("🔐 HUMAN APPROVAL REQUIRED")
        print("═" * 60)
        print(f"  Run ID:   {run_id}")
        print(f"  Tool:     {call.name}()")
        print(f"  Reason:   {reason}")

        if self.config.show_arguments and call.arguments:
            print(f"  Args:     {json.dumps(call.arguments, indent=2, default=str)}")

        print("═" * 60)

        prompt_text = "  Approve?[y/N] + optional feedback: "

        try:
            if self.config.timeout_seconds > 0:
                # Note: If this times out, the underlying thread waiting for input()
                # still exists in Python, but the async flow will correctly move on.
                answer = await asyncio.wait_for(
                    asyncio.to_thread(input, prompt_text),
                    timeout=self.config.timeout_seconds
                )
            else:
                answer = await asyncio.to_thread(input, prompt_text)

        except asyncio.TimeoutError:
            print(f"\n  ⏰ Timeout after {self.config.timeout_seconds}s — auto-rejecting.")
            print("═" * 60 + "\n")
            return HumanGateResult(
                decision=HumanGateDecision.REJECTED,
                feedback=f"Auto-rejected: operator did not respond within {self.config.timeout_seconds}s."
            )

        print("═" * 60 + "\n")

        # Parse answer safely
        answer = answer.strip()
        if not answer:
            approved = False
            feedback = ""
        else:
            parts = answer.split(maxsplit=1)
            first_word = parts[0].lower()
            approved = first_word in ("y", "yes")
            feedback = parts[1] if len(parts) > 1 else ""

        return HumanGateResult(
            decision=HumanGateDecision.APPROVED if approved else HumanGateDecision.REJECTED,
            feedback=feedback or ("Approved by operator." if approved else "Rejected by operator.")
        )