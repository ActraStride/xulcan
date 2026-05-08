"""Tests for ManifestResolver and ResolvedInfrastructure."""

import pytest
from xulcan.runtime.resolver import ManifestResolver
from xulcan.runtime.topology import ResolvedInfrastructure
from xulcan.registry.container import RegistryContainer
from xulcan.registry import bootstrap_registries


@pytest.fixture
def container() -> RegistryContainer:
    """RegistryContainer with all built-in adapters registered."""
    container = RegistryContainer()
    bootstrap_registries(container)
    return container


@pytest.fixture
def canonical_manifest_data() -> dict:
    """Canonical infraprint.yml data from Issue 1."""
    return {
        "version": "1.0.0",
        "kernel": {
            "vault": {"driver": "memory"},
            "ledger": {"driver": "memory"},
            "event_bus": {"driver": "memory"},
            "state_store": {"driver": "memory"}
        },
        "providers": {
            "llm": {
                "default": "gemini",
                "instances": {
                    "gemini": {
                        "driver": "gemini",
                        "model": "gemini-2.5-flash"
                    },
                    "anthropic": {
                        "driver": "anthropic",
                        "model": "claude-3-5-sonnet-20241022"
                    }
                }
            }
        },
        "blueprints": {
            "paths": [],
            "autoload": False
        }
    }


@pytest.mark.asyncio
async def test_resolve_data_canonical_manifest(container: RegistryContainer, canonical_manifest_data: dict):
    """Test end-to-end resolution of canonical infraprint.yml using MemoryVaultStore with pre-loaded secrets."""
    # Pre-load secrets into vault (simulating env vars or external vault)
    vault_secrets = {
        "gemini_api_key": "test_gemini_key",
        "anthropic_api_key": "test_anthropic_key"
    }
    # Override the vault params to include initial secrets
    canonical_manifest_data["kernel"]["vault"]["params"] = {"initial_secrets": vault_secrets}

    resolver = ManifestResolver(container)
    infra = await resolver.resolve_data(canonical_manifest_data)

    # Verify ResolvedInfrastructure structure
    assert isinstance(infra, ResolvedInfrastructure)
    assert infra.manifest.version == "1.0.0"
    assert infra.default_llm == "gemini"

    # Verify LLM instances
    assert "gemini" in infra.llm_instances
    assert "anthropic" in infra.llm_instances
    assert len(infra.llm_instances) == 2

    # Verify infrastructure adapters
    assert infra.vault is not None
    assert infra.ledger is not None
    assert infra.event_bus is not None
    assert infra.state_store is not None


@pytest.mark.asyncio
async def test_missing_vault_key_logs_warning(container: RegistryContainer, canonical_manifest_data: dict, caplog):
    """Test that missing vault key logs a warning but does not raise."""
    # No secrets pre-loaded
    canonical_manifest_data["kernel"]["vault"]["params"] = {}

    resolver = ManifestResolver(container)
    infra = await resolver.resolve_data(canonical_manifest_data)

    # Should still succeed but with warnings
    assert isinstance(infra, ResolvedInfrastructure)
    assert "No secret found for LLM instance" in caplog.text


@pytest.mark.asyncio
async def test_custom_vault_key_override(container: RegistryContainer, canonical_manifest_data: dict):
    """Test vault_key override in LLMInstanceConfig.params."""
    vault_secrets = {
        "custom_gemini_key": "test_gemini_key",
        "anthropic_api_key": "test_anthropic_key"
    }
    canonical_manifest_data["kernel"]["vault"]["params"] = {"initial_secrets": vault_secrets}
    # Override vault_key for gemini
    canonical_manifest_data["providers"]["llm"]["instances"]["gemini"]["params"] = {
        "vault_key": "custom_gemini_key"
    }

    resolver = ManifestResolver(container)
    infra = await resolver.resolve_data(canonical_manifest_data)

    assert isinstance(infra, ResolvedInfrastructure)
    assert "gemini" in infra.llm_instances