"""AgentBlueprint — The agent's soul. Portable, infrastructure-agnostic.

Design Contract:
    The Blueprint defines WHAT the agent is and HOW it thinks.
    It does NOT know WHERE it runs or WHICH infrastructure it uses.

    Cognitive parameters (model, temperature) live in model: ModelSpec.
    They belong here because they define the agent's personality.

    Infrastructure parameters (api_key, db_url) NEVER appear here.
    They live in app.py / VaultStore.

Portability Test:
    You should be able to take agent.yml from local dev (Docker + InMemory)
    to production (AWS + Postgres + Redis) without changing a single line.
"""

from __future__ import annotations

import warnings
from typing import Any

from pydantic import Field, model_validator, AliasChoices

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    DisplayName,
    SemanticText,
    JsonDict,
    SemanticVersion,
    ContextKey,
)
from xulcan.blueprint.types import (
    ModelSpec,          # Canonical ModelSpec from contracts.py
    StrategyConfig,     # For context strategy
    GovernanceConfig,   # For governance (budget only)
    BlueprintSnapshot,
)
from xulcan.blueprint.components import AgentToolConfig, LifecycleConfig


# ═══════════════════════════════════════════════════════════════════════════
# AGENT BLUEPRINT
# ═══════════════════════════════════════════════════════════════════════════

class AgentBlueprint(ImmutableRecord):
    """The static configuration for an agent — its DNA.

    This is the Blueprint dimension of Xulcan's Trinity.

    What lives here (Soul / Cognition):
        - Identity: id, name, version, description
        - Thinking: model (ModelSpec with provider, name, temperature, etc.)
        - Attention: context (StrategyConfig)
        - Skills: tools, lifecycle
        - Personality: system_prompt

    What does NOT live here (Body / Infrastructure):
        - API keys → VaultStore / app.py
        - Database choice → app.py (InMemoryLedger vs PostgresLedger)
        - Memory backend → app.py (MemoryStateStore vs RedisStateStore)
        - Sandbox runtime → app.py (DockerProvider vs FirecrackerProvider)
    """
    xulcan_version: str = Field(
        default="2.0",
        description="Versión del esquema del blueprint."
    )
    # ── Identity ──────────────────────────────────────────────────────────
    id: MachineID = Field(
        description="Unique agent identifier (e.g. 'customer-support-v1')."
    )
    name: DisplayName = Field(
        description="Human-readable agent name."
    )
    version: SemanticVersion = Field(
        default="1.0.0",
        description="Semantic version of this blueprint."
    )
    description: SemanticText = Field(
        default="",
        description="What this agent does and when to use it."
    )

    # ── Cognition (LLM) ───────────────────────────────────────────────────
    model: ModelSpec = Field(
        description=(
            "Complete LLM model specification. "
            "Supports slash syntax: 'google/gemini-2.5-flash' "
            "or explicit form with provider, name, temperature, max_tokens, params."
        )
    )

    fallbacks: list[ModelSpec] = Field(
        default_factory=list,
        description="Ordered list of fallback models to try if the primary fails."
    )

    # ── Attention (Context Strategy) ──────────────────────────────────────
    context: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="full_history"),
        description="Context management strategy with optional parameters."
    )

    # ── Personality ───────────────────────────────────────────────────────
    system_prompt: SemanticText = Field(
        description="Instructions that define the agent's behavior. Supports Jinja2."
    )

    # ── Skills ────────────────────────────────────────────────────────────
    tools: list[AgentToolConfig] = Field(
        default_factory=list,
        description="Available tools with their configurations."
    )
    lifecycle: LifecycleConfig = Field(
        default_factory=LifecycleConfig,
        description="Lifecycle hooks (on_start, on_finish, on_error)."
    )

    # ── Execution Constraints ─────────────────────────────────────────────
    timeout_seconds: float = Field(
        default=600.0,
        ge=1.0,
        le=3600.0,
        description="Maximum execution time in seconds before forced termination."
    )

    # ── Governance (Budget Only) ──────────────────────────────────────────
    governance: GovernanceConfig = Field(
        default_factory=GovernanceConfig,
        description=(
            "Blueprint-level governance configuration. "
            "Currently includes budget enforcement only. "
            "Sentinel and HumanGate policies live in ToolGovernanceConfig per-tool."
        )
    )

    # ═══════════════════════════════════════════════════════════════════════
    # THE SUGAR BOWL (YAML Ergonomics)
    # ═══════════════════════════════════════════════════════════════════════

    @model_validator(mode='before')
    @classmethod
    def _apply_sugar(cls, data: Any) -> Any:
        """Transforms raw dict (from YAML) into Xulcan's strict structure.

        This parser normalizes ergonomic YAML shortcuts into canonical form:
        1. Tools as strings: ["search"] → [{"name": "search"}]
        2. Lifecycle arrow syntax: "tool -> var" → {tool, output_variable}
        """
        if not isinstance(data, dict):
            return data

        # ── 1. Sugar: Tools as Strings ───────────────────────────────────
        if "tools" in data and isinstance(data["tools"], list):
            data["tools"] = [
                {"name": t} if isinstance(t, str) else t
                for t in data["tools"]
            ]

        # ── 2. Sugar: Lifecycle Arrow Syntax ──────────────────────────────
        # "tool_name -> output_var" → {tool: "tool_name", output_variable: "output_var"}
        if "lifecycle" in data and isinstance(data["lifecycle"], dict):
            for stage in ["on_start", "on_finish", "on_error"]:
                if stage in data["lifecycle"] and isinstance(data["lifecycle"][stage], list):
                    new_hooks = []
                    for hook in data["lifecycle"][stage]:
                        if isinstance(hook, str) and "->" in hook:
                            tool_part, var_part = hook.split("->", 1)
                            new_hooks.append({
                                "tool": tool_part.strip(),
                                "output_variable": var_part.strip()
                            })
                        else:
                            new_hooks.append(hook)
                    data["lifecycle"][stage] = new_hooks

        return data

    # ═══════════════════════════════════════════════════════════════════════
    # BLUEPRINT SNAPSHOT
    # ═══════════════════════════════════════════════════════════════════════

    def to_snapshot(self) -> BlueprintSnapshot:
        """
        Genera una versión inmutable y ligera del Blueprint para el Ledger.
        Filtra herramientas y prompts, dejando solo la configuración cognitiva.
        """
        # Importamos aquí para evitar colisiones circulares si las hubiera
        from xulcan.blueprint.types import BlueprintSnapshot
        
        return BlueprintSnapshot(
            id=self.id,
            version=self.version,
            model=self.model,
            governance=self.governance,
            # Extraemos solo el nombre de la estrategia (MachineID)
            context_strategy=self.context.strategy 
        )


    # ── Derived Properties ────────────────────────────────────────────────

    @property
    def all_active_tools(self) -> list[str]:
        """Tool names available to the Kernel (Lifecycle + LLM). Used for validation."""
        return [t.name for t in self.tools if t.enabled]

    @property
    def llm_tools(self) -> list[str]:
        """Tool names visible to the LLM. Only enabled AND exposed tools."""
        return [t.name for t in self.tools if t.enabled and t.exposed]

    @property
    def has_llm_tools(self) -> bool:
        """True if the agent has at least one tool exposed to the LLM."""
        return len(self.llm_tools) > 0

    # ── Validation ────────────────────────────────────────────────────────

    @model_validator(mode='after')
    def validate_tool_coherence(self) -> AgentBlueprint:
        """Ensures no duplicate tools and lifecycle hooks reference valid tools."""
        tool_names = [t.name for t in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("Duplicate tool names found in agent configuration.")

        active_tools = set(self.all_active_tools)
        for stage_name, hooks in [
            ("on_start", self.lifecycle.on_start),
            ("on_finish", self.lifecycle.on_finish),
            ("on_error", self.lifecycle.on_error)
        ]:
            for hook in hooks:
                if hook.tool not in active_tools:
                    raise ValueError(
                        f"Lifecycle '{stage_name}' references tool '{hook.tool}', "
                        f"but it is not present or enabled in the agent's tools list."
                    )
        return self

    @model_validator(mode='after')
    def warn_if_budget_without_enforcement(self) -> AgentBlueprint:
        """Warns the user if a budget is declared but the Bursar won't enforce it."""
        if (
            self.governance.budget.strategy not in ("unlimited", "passthrough")
            and self.governance.budget.strategy == "unlimited"
        ):
            warnings.warn(
                f"Agent '{self.id}' defines governance.budget, but strategy "
                f"is set to 'unlimited'. The budget limits will be IGNORED. "
                f"Set a different budget strategy in your YAML to apply them.",
                UserWarning,
                stacklevel=2
            )
        return self
