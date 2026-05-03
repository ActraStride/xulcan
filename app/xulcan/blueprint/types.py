"""
Core type contracts for the Xulcan framework.

This module defines the fundamental type definitions used across the framework:
- ModelSpec: Complete specification of an LLM model
- StrategyConfig: Typed strategy references with initialization parameters
- GovernanceConfig: Blueprint-level budget configuration
- ToolGovernanceConfig: Per-tool governance settings
- BlueprintSnapshot: Immutable snapshot of agent blueprint for run reproducibility
- BaseContextConfig: Universal base parameters for context strategies

These contracts are the foundational types that bridge the configuration,
execution, and history layers of the framework.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator, AliasChoices

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    ExternalID,
    SemanticVersion,
    FinitePositiveFloat,
    JsonDict,
)


# =============================================================================
# MODEL SPEC
# =============================================================================

class ModelSpec(ImmutableRecord):
    """Complete, typed specification of an LLM model.

    Replaces the flat model_provider (ModelProvider enum) + model_params (JsonDict)
    pattern in AgentBlueprint with a structured, validated record.

    Supports slash syntax for compact YAML declarations:
        model: google/gemini-2.5-flash
    instead of:
        model:
          provider: google
          name: gemini-2.5-flash

    provider maps to the ProviderRegistry key in app.py, exactly as
    ModelProvider enum values did — no registry changes required.

    temperature and max_tokens are promoted to first-class fields because
    they are universal LLM parameters. Provider-specific parameters that
    don't have canonical names (top_p, seed, stop_sequences, etc.) go in
    params and are forwarded to the adapter's ConfigSchema as-is.

    Attributes:
        provider: LLM provider key (maps to ProviderRegistry entry in app.py).
        name: Model name as the provider expects it in its API.
        temperature: Sampling temperature. 0.0 = maximally deterministic.
        max_tokens: Maximum tokens in the response. None = provider default.
        params: Provider-specific parameters forwarded to adapter's ConfigSchema.

    Examples:
        # Slash syntax:
        ModelSpec.model_validate("google/gemini-2.5-flash")
        # → ModelSpec(provider="google", name="gemini-2.5-flash")

        # Full form:
        ModelSpec(
            provider="anthropic",
            name="claude-3-5-sonnet-20241022",
            temperature=0.3,
            max_tokens=4096
        )
    """
    provider: MachineID = Field(
        description="LLM provider key (maps to ProviderRegistry entry in app.py)."
    )
    name: ExternalID = Field(
        description=(
            "Model name as the provider expects it in its API "
            "(e.g. 'gemini-2.5-flash', 'claude-3-5-sonnet-20241022'). "
            "Validated as ExternalID — liberal rules, strict safety."
        )
    )
    temperature: FinitePositiveFloat = Field(
        default=0.0,
        description="Sampling temperature. 0.0 = maximally deterministic."
    )
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum tokens in the response. "
            "None = provider default (adapter decides)."
        )
    )
    params: JsonDict = Field(
        default_factory=dict,
        description=(
            "Provider-specific parameters not covered by the standard fields "
            "(e.g. top_p, seed, stop_sequences). "
            "Forwarded to the adapter's ConfigSchema as-is. "
            "Intentional: these are provider params, not Blueprint-level params."
        )
    )

    @model_validator(mode='before')
    @classmethod
    def parse_slash_syntax(cls, value: Any) -> Any:
        """Expand 'provider/model-name' string into a ModelSpec dict.

        Called before field validation, so all other validators still run
        on the expanded dict.

        Args:
            value: The value to parse (may be a string or dict).

        Returns:
            A dict with 'provider' and 'name' keys if input was a string,
            otherwise the original value unchanged.

        Raises:
            ValueError: If the string doesn't contain exactly one '/' or
                either side of the split is empty.
        """
        if isinstance(value, str):
            parts = value.split("/", 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(
                    f"Invalid ModelSpec string '{value}'. "
                    "Expected 'provider/model-name' format "
                    "(e.g. 'google/gemini-2.5-flash', 'anthropic/claude-3-5-sonnet-20241022')."
                )
            return {"provider": parts[0].strip(), "name": parts[1].strip()}
        return value


# =============================================================================
# STRATEGY CONFIG
# =============================================================================

class StrategyConfig(ImmutableRecord):
    """A typed strategy reference with its initialization parameters.

    Replaces every strategy_name: MachineID + strategy_params: JsonDict
    pair in the Blueprint with a single structured record.

    Supports three syntactic forms for YAML ergonomics:

    1. String shorthand (strategy with no params):
        budget: unlimited
        → StrategyConfig(strategy="unlimited", params={})

    2. Nested dict shorthand (strategy with params):
        budget:
          enforced:
            token_limit: 50000
        → StrategyConfig(strategy="enforced", params={"token_limit": 50000})

    3. Explicit canonical form (always accepted):
        budget:
          strategy: enforced
          params:
            token_limit: 50000
        → StrategyConfig(strategy="enforced", params={"token_limit": 50000})

    The strategy value maps to the relevant Registry key (BursarRegistry,
    SentinelRegistry, HumanGateRegistry, ContextRegistry).

    Attributes:
        strategy: Strategy key (maps to the relevant Registry entry).
        params: Parameters forwarded to the strategy's ConfigSchema constructor.
    """
    strategy: MachineID = Field(
        description="Strategy key (maps to the relevant Registry entry)."
    )
    params: JsonDict = Field(
        default_factory=dict,
        description=(
            "Parameters forwarded to the strategy's ConfigSchema constructor. "
            "Empty dict = strategy uses all defaults."
        )
    )

    @model_validator(mode='before')
    @classmethod
    def parse_fluid(cls, value: Any) -> Any:
        """Normalize fluid YAML syntax into canonical StrategyConfig dict.

        Handles string shorthand and nested dict shorthand.
        Canonical form passes through unchanged.

        Args:
            value: The value to normalize (may be a string, dict, or other).

        Returns:
            A dict with 'strategy' and 'params' keys if input was a string or dict,
            otherwise the original value unchanged.

        Raises:
            ValueError: If a dict is provided but matches neither canonical
                form nor single-key shorthand.
        """
        if isinstance(value, str):
            return {"strategy": value.strip(), "params": {}}

        if isinstance(value, dict):
            # Canonical form: already has 'strategy' key
            if "strategy" in value:
                return value
            # Nested shorthand: {strategy_name: params_dict}
            # e.g. {"enforced": {"token_limit": 50000}}
            if len(value) == 1:
                strategy_name, params = next(iter(value.items()))
                return {"strategy": strategy_name, "params": params or {}}
            raise ValueError(
                f"Ambiguous StrategyConfig dict: {value!r}. "
                "Use either {'strategy': name, 'params': {...}} (canonical) "
                "or {strategy_name: params_dict} (shorthand) — not both."
            )

        return value


# =============================================================================
# GOVERNANCE CONFIGS
# =============================================================================

class GovernanceConfig(ImmutableRecord):
    """Blueprint-level governance: budget only.

    sentinel and human_gate have been moved to ToolGovernanceConfig because
    they are per-tool concerns, not per-agent concerns. Applying them at the
    Blueprint level was too coarse — different tools have different risk profiles
    and should carry their own policy independently.

    Migration alias: 'bursar' is accepted as an alias for 'budget' to ease
    migration from the old flat schema (bursar_strategy + bursar_params).
    The alias is validation-only; serialization always uses 'budget'.

    Attributes:
        budget: Budget enforcement strategy. Defaults to 'unlimited'.

    YAML example:
        governance:
          budget: enforced          # string shorthand
          # or:
          budget:
            enforced:
              token_limit: 50000    # nested shorthand
    """
    budget: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="unlimited"),
        validation_alias=AliasChoices("budget", "bursar"),
        description=(
            "Budget enforcement strategy. "
            "Defaults to 'unlimited' (no enforcement). "
            "Use 'enforced' with token_limit / time_limit_ms to cap consumption."
        )
    )


class ToolGovernanceConfig(ImmutableRecord):
    """Per-tool governance: policy enforcement, human approval, and execution constraints.

    Lives in AgentToolConfig. Each tool declares its own governance independently.
    Defaults are intentionally safe: no policy checks, no approval required,
    read-only, no sandbox.

    The 'sentinel' and 'human_gate' that previously lived at Blueprint level
    are now here. This enables future enterprise use cases where tool X
    (e.g. 'send_email') requires human approval while tool Y (e.g. 'read_file')
    is fully automated.

    Attributes:
        human_gate: How to obtain human approval when the Sentinel escalates.
        sentinel: Tool call policy enforcement strategy.
        side_effects: Declared side-effect profile of this tool.
        sandbox: Whether to execute this tool inside a sandboxed environment.
    """
    human_gate: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="auto_approve"),
        description=(
            "How to obtain human approval when the Sentinel escalates. "
            "Defaults to 'auto_approve' (no approval needed). "
            "Use 'terminal' or 'webhook' for real approval flows."
        )
    )
    sentinel: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="passthrough"),
        description=(
            "Tool call policy enforcement strategy. "
            "Defaults to 'passthrough' (no policy checks). "
            "Use 'blocklist' or 'allowlist' for real enforcement."
        )
    )
    side_effects: Literal["read", "write"] = Field(
        default="read",
        description=(
            "Declared side-effect profile of this tool. "
            "'read'  = does not mutate external state (idempotent safe). "
            "'write' = may mutate external state (triggers stricter governance). "
            "Honest declaration is the operator's responsibility."
        )
    )
    sandbox: bool = Field(
        default=False,
        description=(
            "Whether to execute this tool inside a sandboxed environment. "
            "Requires a SandboxProvider configured in app.py. "
            "Ignored if no SandboxProvider is registered."
        )
    )


# =============================================================================
# BLUEPRINT SNAPSHOT
# =============================================================================

class BlueprintSnapshot(ImmutableRecord):
    """Immutable, reproducible subset of an AgentBlueprint.

    Travels with a run for its entire lifecycle. Stored in RunCreated events
    so the Ledger can replay any historical run without requiring the original
    Blueprint to still exist in its original form or version.

    Subset selection rationale:
        Included — fields that affect the reproducibility of the agent's
        cognitive behavior: model choice, budget governance, context strategy.

        Excluded — infrastructure concerns that vary by deployment environment
        and don't affect what the agent thinks or decides:
            - timeout_seconds (operational, not cognitive)
            - tools (stored separately via RunCreated.tool_names)
            - system_prompt (stored in RunCreated.system_prompt_hash)
            - api_key, db_url, etc. (never in the Blueprint by design)

    Attributes:
        id: Agent blueprint identifier at time of run.
        version: Blueprint semantic version at time of run.
        model: LLM model spec at time of run (provider + name + params).
        governance: Budget governance config at time of run.
        context_strategy: Context strategy key at time of run.
    """
    id: MachineID = Field(
        description="Agent blueprint identifier at time of run."
    )
    version: SemanticVersion = Field(
        description="Blueprint semantic version at time of run."
    )
    model: ModelSpec = Field(
        description="LLM model spec at time of run (provider + name + params)."
    )
    governance: GovernanceConfig = Field(
        description="Budget governance config at time of run."
    )
    context_strategy: MachineID = Field(
        description="Context strategy key at time of run."
    )


# =============================================================================
# BASE CONTEXT CONFIG
# =============================================================================

class BaseContextConfig(ImmutableRecord):
    """Universal base parameters for all context strategies.

    Migrated to core/contracts.py so the blueprint layer can import the config
    base without pulling in the full context engine machinery (BaseContextStrategy
    ABC, UnifiedMessage protocol types, Jinja2 rendering, etc.).

    The strategy ABC (BaseContextStrategy) remains in context/base.py.
    Concrete strategy configs subclass this and add their specific params:

        class SlidingWindowConfig(BaseContextConfig):
            max_messages: int = 10
    """
    pass
