# xulcan/runtime/loaders/manifest_resolver.py
"""ManifestResolver — Stage-1 of Xulcan's runtime materialization pipeline.

Reads an InfraprintManifest and produces a ResolvedInfrastructure.
This is the first async-native component in the boot pipeline.
"""

from __future__ import annotations

import yaml
import logging
from pathlib import Path
from typing import Union, Any

from xulcan.manifest.schema import InfraprintManifest
from xulcan.registry.container import RegistryContainer
from xulcan.runtime.topology import ResolvedInfrastructure
from xulcan.llm.base import BaseLLMAdapter

logger = logging.getLogger("xulcan.runtime.loaders.manifest_resolver")


class ManifestResolver:
    """Reads an InfraprintManifest and materializes it into ResolvedInfrastructure.

    Responsibilities:
        1. Parse and validate the YAML manifest.
        2. Instantiate vault first — the credential source for all LLM instances.
        3. Resolve credentials from vault before adapter construction.
        4. Instantiate all infrastructure adapters.
        5. Return ResolvedInfrastructure for the assembler.

    Does NOT:
        - Build ProtoKernel (Issue 4)
        - Load AgentBlueprints (Issue 4)
        - Wire tool executors (Issue 4)

    Usage:
        container = RegistryContainer()
        bootstrap_registries(container)

        resolver = ManifestResolver(container)
        infra = await resolver.load("infraprint.yml")
    """

    def __init__(self, container: RegistryContainer):
        self._container = container

    async def load(self, path: Union[str, Path]) -> ResolvedInfrastructure:
        """Parse and resolve an infraprint manifest from disk.

        Args:
            path: Path to the infraprint.yml file.

        Returns:
            ResolvedInfrastructure with all adapters instantiated.

        Raises:
            FileNotFoundError: If the manifest file does not exist.
            ValueError: If manifest fails schema validation or a required
                        adapter is not registered in the container.
        """
        manifest = self._parse(path)
        return await self._resolve(manifest)

    async def resolve_data(self, data: dict[str, Any]) -> ResolvedInfrastructure:
        """Resolve from an already-parsed dict.

        Skips filesystem IO entirely. Intended for test isolation and
        programmatic manifest construction.

        Args:
            data: Raw dict conforming to InfraprintManifest schema.

        Returns:
            ResolvedInfrastructure with all adapters instantiated.
        """
        manifest = InfraprintManifest.model_validate(data)
        return await self._resolve(manifest)

    # ── Private ───────────────────────────────────────────────────────────

    def _parse(self, path: Union[str, Path]) -> InfraprintManifest:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Infraprint manifest not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            raise ValueError(f"Infraprint manifest is empty: {path}")
        return InfraprintManifest.model_validate(data)

    async def _resolve(self, manifest: InfraprintManifest) -> ResolvedInfrastructure:
        # ── 1. Vault first ────────────────────────────────────────────────
        # Must be instantiated before any other adapter.
        # It is the credential source for all LLM instances.
        vault = self._container.vault.build(
            manifest.kernel.vault.driver,
            dict(manifest.kernel.vault.params or {})
        )
        logger.debug(f"✓ Vault: driver={manifest.kernel.vault.driver}")

        # ── 2. LLM instances ──────────────────────────────────────────────
        # Credentials are resolved from vault BEFORE calling registry.build().
        # No asyncio bridges inside ProviderRegistry — IO stays here.
        #
        # Vault key convention: {driver}_api_key
        #   "gemini"    → vault.get_secret("gemini_api_key")    → GEMINI_API_KEY
        #   "anthropic" → vault.get_secret("anthropic_api_key") → ANTHROPIC_API_KEY
        #
        # Override via LLMInstanceConfig.params["vault_key"] when the env var
        # does not follow the standard pattern.
        # ── 2. Remaining infrastructure ───────────────────────────────────
        # Build the EventBus before the Ledger because the Ledger may emit
        # firehose events through the bus during runtime.
        event_bus = self._container.event_bus.build(
            manifest.kernel.event_bus.driver,
            dict(manifest.kernel.event_bus.params or {})
        )
        logger.debug(f"✓ EventBus: driver={manifest.kernel.event_bus.driver}")

        ledger = self._container.ledger.build(
            manifest.kernel.ledger.driver,
            {**dict(manifest.kernel.ledger.params or {}), "event_bus": event_bus}
        )
        state_store = self._container.state_store.build(
            manifest.kernel.state_store.driver,
            dict(manifest.kernel.state_store.params or {})
        )

        logger.debug(
            f"✓ Infrastructure: "
            f"ledger={manifest.kernel.ledger.driver} "
            f"bus={manifest.kernel.event_bus.driver} "
            f"state_store={manifest.kernel.state_store.driver}"
        )

        llm_instances: dict[str, BaseLLMAdapter] = {}

        for name, cfg in manifest.providers.llm.instances.items():
            params = {"model_name": cfg.model, **dict(cfg.params or {})}

            if "api_key" not in params:
                vault_key = params.pop("vault_key", f"{cfg.driver}_api_key")
                api_key = await vault.get_secret(vault_key)
                if api_key:
                    params["api_key"] = api_key
                else:
                    logger.warning(
                        f"⚠ No secret found for LLM instance '{name}' "
                        f"(driver={cfg.driver}, vault_key={vault_key}). "
                        f"Adapter may fail at inference time."
                    )

            llm_instances[name] = self._container.llm.build(cfg.driver, params)
            logger.debug(f"✓ LLM: {name} (driver={cfg.driver})")

        return ResolvedInfrastructure(
            manifest=manifest,
            llm_instances=llm_instances,
            default_llm=manifest.providers.llm.default,
            ledger=ledger,
            event_bus=event_bus,
            state_store=state_store,
            vault=vault,
        )
