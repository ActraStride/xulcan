"""Xulcan Registry Package.

This package provides infrastructure for dependency injection and credential management.

Key exports:
    - ProviderRegistry: Generic abstract factory for all adapters
    - CredentialProxy: Injects credentials into adapters at build time
    - ToolSecretsVault: Vault for tool-specific credentials
    - RegistryContainer: Autocontained holder for all Xulcan registries (Issue 23)
    - bootstrap_registries: Pure function to populate RegistryContainer (Issue 23)
"""

from .base import ProviderRegistry
from .credentials import CredentialProxy, ToolSecretsVault
from .container import RegistryContainer
from .bootstrap import bootstrap_registries

__all__ = [
    "ProviderRegistry",
    "CredentialProxy",
    "ToolSecretsVault",
    "RegistryContainer",
    "bootstrap_registries",
]