"""Core interface contracts for the Xulcan Kernel.

This module defines the abstract protocols (contracts) that all external
adapters must implement. The Kernel depends on these interfaces, NOT on
concrete implementations, enabling true dependency inversion.

Architecture:
    - LLMProvider: Contract for model inference adapters
    - ToolExecutor: Contract for tool execution adapters  
    - LedgerRepository: Contract for event persistence adapters
    - StateStore: Contract for volatile working memory
    - Governance Strategies: Contracts for Bursar, Sentinel, and HumanGate

All interfaces use Protocol (PEP 544) for structural subtyping, allowing
implementations without explicit inheritance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Any, TYPE_CHECKING
from collections.abc import AsyncIterator
from abc import abstractmethod

from ..protocol import (
    UnifiedMessage,
    UnifiedResponse,
    UnifiedChunk,
    ToolDefinition,
    ToolCall,
    ToolMessage,
)
from ..history.events import RunEvent, RunSummary
from ..core.primitives import MachineID

# Safe imports for type hinting without causing circular runtime dependencies
if TYPE_CHECKING:
    from ..core.economics import UsageStats, BudgetConfig
    from xulcan.governance.verdicts import BursarVerdict
    from ..blueprint.schema import AgentBlueprint
    from .environment import SystemEnvironment


# ═══════════════════════════════════════════════════════════════════════════
# LLM PROVIDER INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

class LLMProvider(Protocol):
    """Contract that all LLM adapters must implement.
    
    This protocol defines the interface for language model inference. Adapters
    for different providers (OpenAI, Anthropic, Google, etc.) must implement
    these methods to be compatible with the Xulcan Kernel.
    
    Design Philosophy:
        - Provider-agnostic: Works with any LLM backend.
        - Streaming support: Optional streaming via AsyncIterator.
        - Tool integration: Native support for function calling.
        - Error handling: Implementations must raise specific exceptions.
    """
    
    @abstractmethod
    async def generate(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> UnifiedResponse:
        """Generate a completion from the language model.
        
        This is the core inference method. It takes a conversation history
        (messages), optional tool definitions, and generation parameters,
        then returns a complete response including usage statistics.
        
        Args:
            messages: Conversation history (System, User, Assistant, Tool messages).
            tools: Optional tool definitions for function calling.
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.).
        
        Returns:
            UnifiedResponse with content, usage stats, and metadata.
        
        Raises:
            ValueError: If messages are malformed or invalid.
            RuntimeError: If the provider API fails.
        """
        ...
    
    async def generate_stream(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[UnifiedChunk]:
        """Generate a streaming completion from the language model.
        
        Optional method for streaming responses. If not implemented,
        the Kernel will fall back to non-streaming generation.
        
        Yields:
            UnifiedChunk objects containing incremental deltas.
        
        Raises:
            NotImplementedError: If streaming is unsupported by the provider.
        """
        raise NotImplementedError("Streaming not supported by this provider.")
        # Need a yield statement to make it a valid async generator conceptually
        yield UnifiedChunk() # type: ignore


# ... (busca la sección LLM PROVIDER y añade esto debajo)

class LLMOrchestrator(Protocol):
    """Contract for the LLM Orchestration layer (Caching + Fallbacks)."""
    async def generate(
        self,
        blueprint: AgentBlueprint,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> UnifiedResponse:
        ...

# ═══════════════════════════════════════════════════════════════════════════
# TOOL EXECUTOR INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

class ToolExecutor(Protocol):
    """Contract for executing tool calls requested by the model.
    
    This protocol defines how the Kernel dispatches tool execution. 
    Implementations can support local execution, remote APIs, sandboxed
    containers, or any other execution environment.
    """
    
    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolMessage:
        """Execute a single tool call and return the result.
        
        Args:
            call: The tool call to execute (includes name, id, arguments).
        
        Returns:
            ToolMessage with execution result and correlation ID.
            
        Notes:
            - Errors should ideally be returned as ToolMessage with error content,
              not raised as exceptions (to allow the model to see and handle them).
        """
        ...
    
    @abstractmethod
    async def execute_batch(self, calls: list[ToolCall]) -> list[ToolMessage]:
        """Execute multiple tool calls.
        
        Implementations should typically run these concurrently (e.g., using 
        asyncio.gather) and catch individual exceptions so that one failing 
        tool does not crash the entire batch.
        """
        ...

    @abstractmethod
    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Retrieve the JSON schemas for the requested tools."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# LEDGER REPOSITORY INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class LedgerRepository(Protocol):
    """The async contract for the append-only event log.
    
    This interface separates the Kernel (Domain) from the Storage (Infrastructure).
    It enforces the CQRS pattern:
    - Write Side: append()
    - Read Side (History): get_events()
    - Read Side (State): get_summary()
    """

    @abstractmethod
    async def append(self, event: RunEvent) -> None:
        """Atomically persist a new event."""
        ...

    @abstractmethod
    async def get_events(
        self, 
        run_id: MachineID, 
        from_index: int = 0
    ) -> list[RunEvent]:
        """Retrieve the raw timeline for a run (Replay)."""
        ...

    @abstractmethod
    async def get_summary(self, run_id: MachineID) -> RunSummary:
        """Retrieve the current state projection (The 'Fold')."""
        ...

    @abstractmethod
    async def tag_run(self, run_id: MachineID, session_key: str) -> None:
        """Associates a session_key with the most recent run_id."""
        ...

    @abstractmethod
    async def get_last_run_id(self, session_key: str) -> MachineID | None:
        """Retrieves the latest run_id associated with a session_key."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# STATE STORE (BLACKBOARD) INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class StateStore(Protocol):
    """Contract for the Agent's volatile Working Memory (Blackboard).
    
    This interface defines the Shared Memory / IPC (Inter-Process Communication) 
    mechanism. It allows the agent, sub-agents, and tools (like the Sandbox) 
    to pass large payloads by reference instead of passing them by value through 
    the LLM prompt, heavily optimizing token usage.
    
    Architecture Note:
        Implementations (e.g., RedisStateStore) must handle their own 
        serialization/deserialization (JSON/Pickle) since the Kernel 
        will pass native Python types (`Any`).
    """

    @abstractmethod
    async def set(self, run_id: MachineID, key: str, value: Any) -> None:
        """Store a value in the blackboard for a specific run."""
        ...

    @abstractmethod
    async def get(self, run_id: MachineID, key: str) -> Any:
        """Retrieve a value from the blackboard. Returns None if not found."""
        ...

    @abstractmethod
    async def exists(self, run_id: MachineID, key: str) -> bool:
        """Check if a key exists without loading its potentially large payload."""
        ...

    @abstractmethod
    async def keys(self, run_id: MachineID) -> list[str]:
        """List all variable names currently available in this run's memory."""
        ...

    @abstractmethod
    async def delete(self, run_id: MachineID, key: str) -> None:
        """Remove a specific key from the blackboard."""
        ...

    @abstractmethod
    async def clear(self, run_id: MachineID) -> None:
        """Clear all memory for a specific run (Garbage Collection)."""
        ...

# ═══════════════════════════════════════════════════════════════════════════
# VAULT STORE (SECRETS MANAGEMENT) INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

@runtime_checkable
class VaultStore(Protocol):
    """Contract for secure secret retrieval and storage.
    
    This interface manages persistent, global or tenant-level secrets (API keys,
    database passwords), ensuring they are kept out of agent blueprints, 
    volatile memory, and execution logs.
    """

    @abstractmethod
    async def get_secret(self, key: str) -> str | None:
        """Retrieve a secret securely by its key."""
        ...

    @abstractmethod
    async def set_secret(self, key: str, value: str) -> None:
        """Store a secret securely."""
        ...

# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT STRATEGY INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

# En interfaces.py (Más abajo)
@runtime_checkable
class ContextStrategy(Protocol):
    """Contract for managing conversation context sizes and overflow."""
    
    @abstractmethod
    async def build_prompt(
        self,
        messages: list[UnifiedMessage],
        blueprint: AgentBlueprint,
        run_id: MachineID,
        environment: SystemEnvironment | None = None  # <-- CAMBIAR StateStore POR SystemEnvironment
    ) -> list[UnifiedMessage]:
        ...


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE STRATEGY INTERFACES
# ═══════════════════════════════════════════════════════════════════════════
 
# xulcan/kernel/interfaces.py

class BursarStrategy(Protocol):
    """Contract for budget governance strategies."""

    @abstractmethod
    def evaluate(
        self,
        cumulative_usage: UsageStats,
        run_id: MachineID,
        loop_counter: int,
    ) -> BursarVerdict: # ← PASO 11: Usar el Enum de core.contracts
        """
        Determina si el agente puede continuar basándose en el 
        consumo acumulado y su configuración interna.
        """
        ...
 
class SentinelStrategy(Protocol):
    """Contract for tool call policy enforcement strategies.
 
    The Sentinel answers one question per tool call:
        "Is this tool call permitted?"
    """
 
    @abstractmethod
    def evaluate(
        self,
        call: ToolCall,
        run_id: MachineID,
        loop_counter: int,
    ) -> Any:  # Returns SentinelVerdict
        """Evaluate whether a tool call is permitted by policy."""
        ...
 
 
class HumanGateStrategy(Protocol):
    """Contract for human approval mechanism strategies.
 
    The HumanGate answers one question when the Sentinel escalates:
        "How do we obtain human approval for this tool call?"
    """
 
    @abstractmethod
    async def request_approval(
        self,
        call: ToolCall,
        reason: str,
        run_id: MachineID,
    ) -> Any:  # Returns HumanGateVerdict
        """Request human (or simulated) approval for a tool call."""
        ...

# ═══════════════════════════════════════════════════════════════════════════
# EVENT BUS (CENTRAL NERVOUS SYSTEM) INTERFACE
# ═══════════════════════════════════════════════════════════════════════════


@runtime_checkable
class EventBus(Protocol):
    """Contract for real-time pub/sub event distribution.
    
    Serves as the central nervous system of Xulcan OS. Used for:
    1. Firehose (Telemetry): Broadcasting immutable Ledger events to Nexus UI.
    2. IPC (Inter-Process Communication): Real-time agent choreography, 
       tool progress bars, and distributed swarm signals.
    """

    @abstractmethod
    async def publish(self, channel: str, message: str) -> None:
        """Emit a message to a specific channel.
        
        Args:
            channel: The namespace/topic (e.g., 'xulcan:firehose:<run_id>' 
                     or 'xulcan:ipc:<run_id>').
            message: The serialized payload (usually a JSON string).
        """
        ...

    @abstractmethod
    def subscribe(self, channel: str) -> AsyncIterator[str]:
        """Listen to a channel and yield messages in real-time.
        
        Args:
            channel: The namespace/topic to subscribe to. Depending on the 
                     adapter (e.g., Redis), this may support pattern matching 
                     (like 'xulcan:*:<run_id>').
                     
        Yields:
            Serialized message strings exactly as they arrive.
        """
        ...