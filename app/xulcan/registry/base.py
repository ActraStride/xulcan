"""Universal Registry (Abstract Factory) for Xulcan.

This module provides the ProviderRegistry class, which acts as a generic IoC
container and abstract factory for all external adapters (LLMs, Memory,
Ledger, Context, Governance).
"""

from __future__ import annotations

from typing import TypeVar, Generic, Any

T = TypeVar('T')


class ProviderRegistry(Generic[T]):
    """Universal Registry (Abstract Factory) for Xulcan.

    Stores Classes (type[T]), not instances.
    Enables Lazy Loading and boundary validation via ConfigSchema.

    Build Pattern:
        registry.register("gemini", GeminiAdapter)
        adapter = registry.build("gemini", {"api_key": "...", "model_name": "..."})
        # → Validates params against GeminiAdapter.ConfigSchema
        # → Returns a fully instantiated, configured adapter
    """

    def __init__(self, component_name: str = "Component"):
        self._component_name = component_name
        self._providers: dict[str, type[T]] = {}

    def register(self, name: str, provider_class: type[T]) -> None:
        """Register an adapter class. Stores the class, not an instance."""
        self._providers[name] = provider_class

    def get_class(self, name: str) -> type[T]:
        """Returns the class ready for manual instantiation."""
        if name not in self._providers:
            raise ValueError(
                f"{self._component_name} '{name}' not found. "
                f"Available: {self.available_providers}"
            )
        return self._providers[name]

    def build(self, name: str, params: dict[str, Any]) -> T:
        """Validates params against ConfigSchema and returns a configured instance.

        This is the primary instantiation path. It guarantees that:
        1. The adapter exists in the registry.
        2. The params are valid according to the adapter's ConfigSchema.
        3. The returned instance is fully configured and ready to use.

        Args:
            name: The registered adapter name (e.g., "gemini", "memory").
            params: Raw configuration dictionary (from YAML, env, or app.py).

        Returns:
            A fully instantiated adapter of type T.

        Raises:
            ValueError: If adapter not found or params fail ConfigSchema validation.

        Example:
            >>> adapter = llm_registry.build("gemini", {
            ...     "api_key": os.getenv("GEMINI_API_KEY"),
            ...     "model_name": "gemini-2.5-flash",
            ...     "temperature": 0.7
            ... })
        """
        adapter_class = self.get_class(name)

        # If the adapter declares a ConfigSchema, validate before instantiating
        config_schema = getattr(adapter_class, 'ConfigSchema', None)

        if config_schema is not None:
            try:
                config = config_schema(**params)
            except Exception as e:
                raise ValueError(
                    f"Invalid config for {self._component_name} '{name}': {e}"
                ) from e
            return adapter_class(config=config)

        # Fallback for adapters without ConfigSchema (legacy / no-config adapters)
        return adapter_class(**params)

    @property
    def available_providers(self) -> list[str]:
        """List of all registered provider names."""
        return list(self._providers.keys())