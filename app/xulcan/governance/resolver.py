"""GovernanceResolver — Compiles hierarchical Bursar limits at assembly time.

Architecture:
    AppConfig.governance.bursar
            ↓
        GovernanceResolver
            ↓
    CompositeBursarStrategy (if both App AND Agent have limits)
            ↑
AgentBlueprint.governance.bursar

The Kernel receives a pre-compiled BursarStrategy. It never resolves
hierarchy at runtime.

Resolution logic:
    1. Both App and Agent define enforced limits → CompositeBursarStrategy(MIN)
    2. Only Agent defines limit → Agent Bursar directly
    3. Only App defines limit → App Bursar directly (edge case for standalone apps)
    4. Both are unlimited → UnlimitedBursarStrategy directly
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from xulcan.governance.bursar.base import BaseBursarStrategy
from xulcan.governance.bursar.strategies.enforced import EnforcedBursarStrategy
from xulcan.governance.bursar.strategies.unlimited import UnlimitedBursarStrategy
from xulcan.governance.bursar.strategies.composite import CompositeBursarStrategy
from xulcan.contracts import GovernanceConfig

if TYPE_CHECKING:
    from xulcan.manifest.schema import AppConfig
    from xulcan.blueprint.schema import AgentBlueprint

logger = logging.getLogger("xulcan.governance.resolver")


def _is_enforced(config: GovernanceConfig | None) -> bool:
    """Check if a GovernanceConfig has enforced (non-unlimited) budget."""
    if config is None:
        return False
    return config.budget.strategy != "unlimited"


def _build_bursar_from_config(
    config: GovernanceConfig,
    bursar_registry: "ProviderRegistry",
) -> BaseBursarStrategy:
    """Build a BursarStrategy from a GovernanceConfig using the registry."""
    return bursar_registry.build(
        config.budget.strategy,
        config.budget.params or {}
    )


class ProviderRegistry:
    """Forward declaration for type hints."""
    pass


class GovernanceResolver:
    """Compiles App + Agent Bursar into a single effective strategy.

    This is an assembly-time concern, not a runtime concern.
    The Kernel receives a fully resolved strategy and uses it directly.
    """

    def __init__(self, bursar_registry: ProviderRegistry):
        """Initialize resolver with the Bursar registry for strategy instantiation.

        Args:
            bursar_registry: ProviderRegistry[BaseBursarStrategy] from RegistryContainer.
        """
        self._bursar_registry = bursar_registry

    def resolve(
        self,
        app_config: "AppConfig | None",
        agent_blueprint: "AgentBlueprint",
    ) -> BaseBursarStrategy:
        """Resolve the effective Bursar strategy for an agent under an app.

        Args:
            app_config: The AppConfig containing app-level governance, or None.
            agent_blueprint: The AgentBlueprint containing agent-level governance.

        Returns:
            A fully instantiated BursarStrategy:
            - CompositeBursarStrategy if both App and Agent have enforced limits
            - The non-unlimited strategy directly if only one has limits
            - UnlimitedBursarStrategy if neither has enforced limits
        """
        app_governance = app_config.governance if app_config else None
        agent_governance = agent_blueprint.governance

        app_is_enforced = _is_enforced(app_governance)
        agent_is_enforced = _is_enforced(agent_governance)

        logger.debug(
            f"[GovernanceResolver] App enforced: {app_is_enforced}, "
            f"Agent enforced: {agent_is_enforced} "
            f"(agent: {agent_blueprint.id})"
        )

        # Case 1: Both have enforced limits → Composite
        if app_is_enforced and agent_is_enforced:
            logger.debug(f"[GovernanceResolver] Both enforced — creating CompositeBursarStrategy")
            app_bursar = _build_bursar_from_config(app_governance, self._bursar_registry)
            agent_bursar = _build_bursar_from_config(agent_governance, self._bursar_registry)
            return CompositeBursarStrategy(
                app_bursar=app_bursar,
                agent_bursar=agent_bursar,
            )

        # Case 2: Only Agent has enforced limit → Agent Bursar directly
        if agent_is_enforced and not app_is_enforced:
            logger.debug(f"[GovernanceResolver] Agent only — using Agent Bursar directly")
            return _build_bursar_from_config(agent_governance, self._bursar_registry)

        # Case 3: Only App has enforced limit (standalone agent under app) → App Bursar directly
        if app_is_enforced and not agent_is_enforced:
            logger.debug(f"[GovernanceResolver] App only — using App Bursar directly")
            return _build_bursar_from_config(app_governance, self._bursar_registry)

        # Case 4: Neither has enforced limits → UnlimitedBursarStrategy directly
        logger.debug(f"[GovernanceResolver] Neither enforced — using UnlimitedBursarStrategy")
        return UnlimitedBursarStrategy(config=UnlimitedBursarStrategy.ConfigSchema())