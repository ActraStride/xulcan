"""Runtime loaders — Materialization and ingestion boundaries.

This module contains the runtime ingestion pipeline:
- ManifestResolver: materializes declarative infrastructure manifests
- BlueprintLoader: hydrates agent blueprints from YAML
- Compatibility: schema migrations and adapter transforms
"""

from xulcan.runtime.loaders.manifest_resolver import ManifestResolver
from xulcan.runtime.loaders.blueprint_loader import BlueprintLoader
from xulcan.runtime.loaders.app_discovery import AppDiscoveryEngine

__all__ = [
    "ManifestResolver",
    "BlueprintLoader",
    "AppDiscoveryEngine",
]
