"""Xulcan Kernel - The Agent Operating System Runtime.

This package contains the core execution engine that orchestrates agent
behavior, enforces governance policies, and manages the agent lifecycle.

Key Components:
    - interfaces: Abstract contracts for external adapters
    - states: FSM state definitions and transitions
    - orchestrator: Main execution coordinator
    - governance: Budget and policy enforcement (Bursar, Sentinel)
    - context: Memory and conversation management

Architecture:
    The Kernel follows strict dependency inversion. It depends on abstract
    interfaces (protocols), not concrete implementations. This allows any
    LLM provider, tool executor, or storage backend to be plugged in.

Example:
    >>> from xulcan.kernel import Orchestrator
    >>> from xulcan.kernel.interfaces import LLMProvider, ToolExecutor
    >>> 
    >>> orchestrator = Orchestrator(
    ...     llm_provider=my_llm,
    ...     tool_executor=my_tools,
    ...     ledger=my_ledger
    ... )
    >>> result = await orchestrator.run(blueprint, input="Hello")
"""

from .interfaces import (
    LLMProvider,
    ToolExecutor,
    LedgerRepository,
)
from .states import (
    KernelState,
    InvalidTransitionError,
    validate_transition,
    is_terminal_state,
    get_valid_transitions,
)

__all__ = [
    "LLMProvider",
    "ToolExecutor",
    "LedgerRepository",
    "KernelState",
    "InvalidTransitionError",
    "validate_transition",
    "is_terminal_state",
    "get_valid_transitions",
]
