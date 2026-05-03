"""Defines agent configuration types (the "Blueprint" dimension).

This module contains types for defining agent behavior, including model
selection, system prompts, tool configurations, execution parameters, and
lifecycle hooks for orchestrating tool execution at critical points.
Agents in Xulcan are data (JSON/YAML configurations), not code (classes).
"""

from __future__ import annotations

from pydantic import Field

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    ContextKey,
    JsonDict
)
from xulcan.blueprint.types import ToolGovernanceConfig


# ═══════════════════════════════════════════════════════════════════════════
# AGENT CONFIGURATION TYPES
# ═══════════════════════════════════════════════════════════════════════════

class AgentToolConfig(ImmutableRecord):
    """Configuration for a single tool available to an agent.

    Tools can be enabled/disabled without removing them from the configuration.
    The `exposed` flag controls the security boundary between the LLM and
    internal infrastructure tools (like context loaders).

    Attributes:
        name: The tool identifier (must match a registered tool).
        enabled: Whether this tool is currently active in the system.
        exposed: If True, the LLM is aware of this tool and can invoke it.
                 If False, the LLM cannot see it, but Lifecycle hooks can
                 still execute it behind the scenes.
        governance: Per-tool governance configuration (sentinel, human_gate,
                    side_effects, sandbox). Defaults are intentionally safe:
                    no policy checks, auto-approve, read-only, no sandbox.
        blueprint_id: When present, indicates this tool is actually a sub-agent.
                      The Kernel applies two-layer governance (see Xulcan v2).
                      None = normal tool, MachineID = sub-agent blueprint ID.

    Example:
        >>> tool = AgentToolConfig(name="web_search", enabled=True, exposed=True)
        >>> loader = AgentToolConfig(name="load_db", enabled=True, exposed=False)
        >>> subagent = AgentToolConfig(
        ...     name="code_executor",
        ...     enabled=True,
        ...     exposed=True,
        ...     blueprint_id="code-agent-v1",
        ...     governance=ToolGovernanceConfig(
        ...         sentinel={"strategy": "allowlist", "params": {"allowed_tools": ["read_file", "write_file"]}},
        ...         sandbox=True
        ...     )
        ... )
    """
    name: MachineID = Field(
        description="Tool identifier (must match a registered tool in the environment)."
    )

    enabled: bool = Field(
        default=True,
        description="Whether this tool is actively available for execution."
    )

    exposed: bool = Field(
        default=True,
        description="If True, injects the tool schema into the LLM prompt. "
                    "If False, limits execution strictly to Lifecycle hooks."
    )

    # ── Governance ────────────────────────────────────────────────────────
    governance: ToolGovernanceConfig = Field(
        default_factory=ToolGovernanceConfig,
        description=(
            "Per-tool governance configuration. "
            "Defaults are intentionally safe: sentinel=passthrough, "
            "human_gate=auto_approve, side_effects=read, sandbox=False. "
            "Override per-tool for specialized security requirements."
        )
    )

    # ── Sub-agent Indicator ───────────────────────────────────────────────
    # TODO: Implement two-layer governance in Kernel for v2
    #       When blueprint_id is present, the Kernel creates a child FSM
    #       for the sub-agent with its own governance scope.
    blueprint_id: MachineID | None = Field(
        default=None,
        description=(
            "When present, indicates this tool is actually a sub-agent blueprint. "
            "The Kernel applies two-layer governance (see Xulcan v2): "
            "parent governance at the agent level + child governance at the tool level. "
            "None = normal tool execution, MachineID = sub-agent with its own blueprint."
        )
    )


class LifecycleHook(ImmutableRecord):
    """Defines a tool execution instruction within a lifecycle stage.

    This enables "Programmable Agents" by allowing tools to read from and
    write to the agent's dynamic context (StateStore) automatically at
    startup, completion, or upon encountering fatal errors.

    Attributes:
        tool: The identifier of the tool to execute.
        arguments: Static arguments pre-bound to the execution.
        arguments_map: Dynamic state bindings. Keys are tool parameter names;
            values are the StateStore ContextKeys to fetch data from.
        output_variable: The StateStore key where the execution result will
            be saved. If None, the result is treated as fire-and-forget.

    Example:
        >>> hook = LifecycleHook(
        ...     tool="query_vector_db",
        ...     arguments={"top_k": 5},               # Static
        ...     arguments_map={"query": "user_id"},   # Dynamic (from State)
        ...     output_variable="rag_context"         # Save result to State
        ... )
    """
    tool: MachineID = Field(
        description="The identifier of the registered tool to execute."
    )

    arguments: JsonDict = Field(
        default_factory=dict,
        description="Static arguments pre-bound to this execution."
    )

    arguments_map: dict[ContextKey, ContextKey] = Field(
        default_factory=dict,
        description="Maps tool argument names to StateStore variable keys."
    )

    output_variable: ContextKey | None = Field(
        default=None,
        description="Name of the StateStore variable to store the tool's output."
    )


class LifecycleConfig(ImmutableRecord):
    """Configuration for lifecycle hooks that execute tools at critical points.

    Lifecycle hooks enable advanced patterns like RAG (Retrieval-Augmented
    Generation), context injection, and state cleanup without polluting
    the core agent logic with hardcoded API calls.

    The Kernel invokes these hooks sequentially at the specified stage.
    Tools must be registered and `enabled: true` (though they can be `exposed: false`).

    Attributes:
        on_start: Hooks executed before the main agent reasoning loop begins.
            Use cases: RAG retrieval, profile loading, workspace initialization.
        on_finish: Hooks executed after successful agent completion.
            Use cases: Saving conversation summaries, DB commits, notifications.
        on_error: Hooks executed if the agent encounters a fatal error.
            Use cases: Alerting systems, rollback operations, failure logging.

    Design Notes:
        - Hook execution is strictly sequential within each stage.
        - Hooks are optional; empty lists mean no execution.
        - Hook failures generally halt the lifecycle stage (configurable in Kernel).
    """
    on_start: list[LifecycleHook] = Field(
        default_factory=list,
        description="Tools to execute sequentially before the agent loop."
    )

    on_finish: list[LifecycleHook] = Field(
        default_factory=list,
        description="Tools to execute sequentially after a successful run."
    )

    on_error: list[LifecycleHook] = Field(
        default_factory=list,
        description="Tools to execute sequentially upon a fatal error."
    )
