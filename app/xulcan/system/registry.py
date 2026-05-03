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


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL VAULT INTERFACE (PASO 12: Design for future tool credentials)
# ═══════════════════════════════════════════════════════════════════════════════
#
# PROBLEM:
#   Today, CredentialProxy only handles LLM credentials (api_key, host, etc.).
#   When the first external tool arrives (e.g., a Slack tool with its own
#   API key), someone will hardcode it in the @tool decorator or in app.py.
#
# DESIGN GOAL:
#   Provide a clean interface for tool-scoped credentials before the first
#   external tool arrives. This prevents credential leakage and enables
#   proper secret management per tool.
#
# NOT IMPLEMENTED YET — This is the interface contract. Implementation
# requires:
#   - ToolRegistry to store @tool decorated functions
#   - ToolConfig schema for per-tool parameters
#   - Integration with ToolExecutor
#
# USAGE (future):
#   >>> proxy = CredentialProxy(
#   ...     registry=llm_registry,
#   ...     llm_secrets={"gemini": {"api_key": "..."}},
#   ...     tool_secrets={"slack": {"bot_token": "..."}}
#   ... )
#   >>> adapter = proxy.build("slack", {"channel": "#general"})
#   # → Injects bot_token from tool_secrets["slack"]

class ToolSecretsVault:
    """Interface for tool-scoped credential storage.

    This class defines the contract for managing credentials that belong
    to specific tools (not LLM providers). Examples:
        - Slack bot_token
        - GitHub PAT
        - Custom API keys for external services

    Attributes:
        _secrets: Dictionary mapping tool name to secret key-value pairs.
            Example: {"slack": {"bot_token": "xoxb-...", "signing_secret": "..."}}

    Note:
        This is an interface design. Full implementation requires:
        1. Integration with VaultStore / environment variables
        2. Tool registration with @tool decorator
        3. ToolConfig schema per tool
        4. ToolExecutor integration to inject secrets at execution time
    """

    def __init__(self, secrets_map: dict[str, dict[str, Any]] | None = None):
        """Initialize the vault with optional pre-loaded secrets.

        Args:
            secrets_map: Initial secrets mapping.
                Example: {"slack": {"bot_token": "..."}, "github": {"token": "..."}}
        """
        self._secrets: dict[str, dict[str, Any]] = secrets_map or {}

    def register(self, tool_name: str, secrets: dict[str, Any]) -> None:
        """Register credentials for a specific tool.

        Args:
            tool_name: The tool identifier (matches @tool(name="...")).
            secrets: Key-value pairs of secrets for this tool.
                Example: {"api_key": "...", "secret": "..."}

        Example:
            >>> vault = ToolSecretsVault()
            >>> vault.register("slack", {"bot_token": "xoxb-...", "signing_secret": "..."})
        """
        self._secrets[tool_name] = secrets

    def get(self, tool_name: str) -> dict[str, Any] | None:
        """Retrieve secrets for a specific tool.

        Args:
            tool_name: The tool identifier.

        Returns:
            Dictionary of secrets for the tool, or None if not found.

        Example:
            >>> secrets = vault.get("slack")
            >>> if secrets:
            ...     adapter = registry.build("slack", {**params, **secrets})
        """
        return self._secrets.get(tool_name)

    def has(self, tool_name: str) -> bool:
        """Check if secrets exist for a tool.

        Args:
            tool_name: The tool identifier.

        Returns:
            True if secrets are registered for this tool.
        """
        return tool_name in self._secrets

    def inject(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Inject tool secrets into execution params.

        This is the primary method for ToolExecutor integration.

        Args:
            tool_name: The tool identifier.
            params: Original execution parameters.

        Returns:
            Merged params with tool secrets injected.
            If tool has no secrets registered, returns original params unchanged.

        Example:
            >>> params = {"channel": "#general", "message": "Hello"}
            >>> merged = vault.inject("slack", params)
            >>> # merged = {"channel": "#general", "message": "Hello",
            >>> #          "bot_token": "xoxb-...", "signing_secret": "..."}
        """
        secrets = self.get(tool_name)
        if secrets:
            return {**params, **secrets}
        return params


class CredentialProxy(Generic[T]):
    """Generic Transparent Proxy for Just-In-Time Secret Injection.

    Wraps ANY ProviderRegistry (LLMs, Ledgers, VectorDBs) to inject
    credentials without altering the pure registry logic.

    NOTE: For tool credentials (external tools like Slack, GitHub, etc.),
    use ToolSecretsVault instead. CredentialProxy is designed for
    infrastructure components (LLMs, databases), not tool-level secrets.
    """

    def __init__(
        self,
        registry: ProviderRegistry[T],
        llm_secrets: dict[str, dict[str, Any]],
        tool_vault: ToolSecretsVault | None = None
    ):
        """Initialize the proxy.

        Args:
            registry: The underlying ProviderRegistry to wrap.
            llm_secrets: Secrets map for LLM/infrastructure providers.
                Example: {"gemini": {"api_key": "..."}, "postgres": {"password": "..."}}
            tool_vault: Optional vault for tool-scoped credentials.
                See ToolSecretsVault for details.
        """
        self._registry = registry
        self._llm_secrets = llm_secrets
        self._tool_vault = tool_vault or ToolSecretsVault()

    def build(self, name: str, params: dict[str, Any]) -> T:
        """Intercepts build(), injects secrets if they exist, and delegates.

        Priority:
            1. LLM secrets (llm_secrets) — for infrastructure components
            2. Tool secrets (tool_vault) — via inject() method
        """
        merged_params = dict(params)

        # Inject LLM/infrastructure secrets
        provider_secrets = self._llm_secrets.get(name)
        if provider_secrets:
            merged_params.update(provider_secrets)

        # Inject tool secrets (for external tools)
        merged_params = self._tool_vault.inject(name, merged_params)

        return self._registry.build(name, merged_params)

    def register(self, name: str, provider_class: type[T]) -> None:
        """Delegates registration to the real registry."""
        self._registry.register(name, provider_class)

    def get_class(self, name: str) -> type[T]:
        """Returns the class from the underlying registry."""
        return self._registry.get_class(name)

    @property
    def available_providers(self) -> list[str]:
        """List of all registered provider names."""
        return self._registry.available_providers

    # ── Tool Vault Access ──────────────────────────────────────────────────

    @property
    def tool_vault(self) -> ToolSecretsVault:
        """Access the tool vault for managing tool-specific credentials."""
        return self._tool_vault

    def register_tool_secret(self, tool_name: str, secrets: dict[str, Any]) -> None:
        """Register credentials for a specific tool.

        Args:
            tool_name: The tool identifier.
            secrets: Key-value pairs of secrets.

        Example:
            >>> proxy.register_tool_secret("slack", {
            ...     "bot_token": "xoxb-...",
            ...     "signing_secret": "..."
            ... })
        """
        self._tool_vault.register(tool_name, secrets)
