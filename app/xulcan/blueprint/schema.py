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
        3. Legacy flat schema mapping: model_provider + model_name → model: ModelSpec
        4. Legacy governance mapping: bursar_strategy → governance.budget
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

        # ── 3. Sugar: Legacy Flat Schema Mapping ─────────────────────────
        # model_provider + model_name + model_params → model: ModelSpec
        if "model_provider" in data and "model" not in data:
            model_data = {
                "provider": data.pop("model_provider"),
            }
            # Extract known cognitive params from model_params if present
            if "model_params" in data:
                params = data.pop("model_params", {})
                model_data["name"] = params.pop("model_name", params.pop("name", "unknown"))
                # temperature and max_tokens are first-class in ModelSpec
                if "temperature" in params:
                    model_data["temperature"] = params.pop("temperature")
                if "max_tokens" in params:
                    model_data["max_tokens"] = params.pop("max_tokens")
                # Remaining params go to ModelSpec.params
                if params:
                    model_data["params"] = params
                elif "model_name" in data:
                    model_data["name"] = data.pop("model_name")
                elif "temperature" in data:
                    model_data["temperature"] = data.pop("temperature")
                elif "max_tokens" in data:
                    model_data["max_tokens"] = data.pop("max_tokens")
            else:
                # Legacy fields at root level
                model_data["name"] = data.pop("model_name", "unknown")
                model_data["temperature"] = data.pop("temperature", 0.0)
                if "max_tokens" in data:
                    model_data["max_tokens"] = data.pop("max_tokens")
            data["model"] = model_data

        # ── 4. Sugar: Legacy Governance Mapping ───────────────────────────
        # bursar_strategy + bursar_params → governance.budget: StrategyConfig
        if "bursar_strategy" in data and "governance" not in data:
            data["governance"] = {
                "budget": {
                    "strategy": data.pop("bursar_strategy"),
                }
            }
            if "bursar_params" in data:
                bursar_params = data.pop("bursar_params", {})
                if bursar_params:
                    data["governance"]["budget"]["params"] = bursar_params

        # ── 5. Sugar: Legacy Context Mapping ──────────────────────────────
        # context_strategy + context_params → context: StrategyConfig
        if "context_strategy" in data and "context" not in data:
            context_data = {"strategy": data.pop("context_strategy")}
            if "context_params" in data:
                params = data.pop("context_params", {})
                if params:
                    context_data["params"] = params
            data["context"] = context_data

        return data

    # ═══════════════════════════════════════════════════════════════════════
    # COMPATIBILITY BRIDGE (The Strangler Fig)
    # Temporary properties to keep runtime.py working during the transition.
    # These will be removed in the second pass post-refactor.
    # ═══════════════════════════════════════════════════════════════════════
    # Dentro de la clase AgentBlueprint en xulcan/blueprint/schema.py

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


    @property
    def model_provider(self) -> str:
        """[DEPRECATED] Bridge property — use model.provider instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use model.provider.
        """
        return self.model.provider

    @property
    def model_name(self) -> str:
        """[DEPRECATED] Bridge property — use model.name instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use model.name.
        """
        return self.model.name

    @property
    def temperature(self) -> float:
        """[DEPRECATED] Bridge property — use model.temperature instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use model.temperature.
        """
        return self.model.temperature

    @property
    def max_tokens(self) -> int | None:
        """[DEPRECATED] Bridge property — use model.max_tokens instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use model.max_tokens.
        """
        return self.model.max_tokens

    @property
    def bursar_strategy(self) -> str:
        """[DEPRECATED] Bridge property — use governance.budget.strategy instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use governance.budget.strategy.
        """
        return self.governance.budget.strategy

    @property
    def bursar_params(self) -> JsonDict:
        """[DEPRECATED] Bridge property — use governance.budget.params instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use governance.budget.params.
        """
        return self.governance.budget.params

    @property
    def context_strategy(self) -> str:
        """[DEPRECATED] Bridge property — use context.strategy instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use context.strategy.
        """
        return self.context.strategy

    @property
    def context_params(self) -> JsonDict:
        """[DEPRECATED] Bridge property — use context.params instead.

        This property exists for compatibility during the refactor transition.
        Delete after runtime.py is updated to use context.params.
        """
        return self.context.params

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
