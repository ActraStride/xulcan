"""Xulcan Registry Package.

This package provides infrastructure for dependency injection and credential management.

Key exports:
    - ProviderRegistry: Generic abstract factory for all adapters
    - ToolSecretsVault: Vault for tool-specific credentials
    - RegistryContainer: Autocontained holder for all Xulcan registries (Issue 23)
    - bootstrap_registries: Pure function to populate RegistryContainer (Issue 23)
"""

from .base import ProviderRegistry
from .credentials import ToolSecretsVault
from .container import RegistryContainer
from .bootstrap import bootstrap_registries

__all__ = [
    "ProviderRegistry",
    "ToolSecretsVault",
    "RegistryContainer",
    "bootstrap_registries",
]