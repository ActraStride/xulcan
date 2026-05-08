"""bootstrap_registries — Populate RegistryContainer with all built-in adapters.

This is the single canonical location where Xulcan declares what adapters exist.
No other module should ever call container.*.register() directly.

All imports are local to this module to:
    1. Avoid side effects at module import time.
    2. Keep the boot order explicit and auditable.
    3. Ensure lazy loading of adapter dependencies.

NOTE: Adapters with optional external dependencies (e.g., anthropic, mistral,
cohere) are conditionally registered. If a dependency is missing, a warning is
logged but bootstrap continues.
"""

from __future__ import annotations

import logging
from xulcan.registry.container import RegistryContainer

logger = logging.getLogger("xulcan.registry.bootstrap")


def bootstrap_registries(container: RegistryContainer) -> None:
    """Register all built-in adapters into the provided RegistryContainer.

    This is the single canonical location where Xulcan declares what
    adapters exist. No other module should call container.*.register().

    All imports are local to avoid side effects at module import time
    and to keep boot order explicit.

    Args:
        container: A fresh RegistryContainer to populate.
    """

    # ══════════════════════════════════════════════════════════════════════
    # 1. INFRASTRUCTURE REGISTRIES
    # ══════════════════════════════════════════════════════════════════════

    # ── Ledger ────────────────────────────────────────────────────────────
    from xulcan.ledger.adapters.in_memory import InMemoryLedger

    container.ledger.register("memory", InMemoryLedger)

    # ── Event Bus ─────────────────────────────────────────────────────────
    from xulcan.bus.adapters.in_memory import InMemoryEventBus

    container.event_bus.register("memory", InMemoryEventBus)

    # ── State Store ───────────────────────────────────────────────────────
    from xulcan.memory.state.adapters.in_memory import MemoryStateStore

    container.state_store.register("memory", MemoryStateStore)

    # ── Vault ─────────────────────────────────────────────────────────────
    from xulcan.memory.vault.adapters.in_memory import MemoryVaultStore

    container.vault.register("memory", MemoryVaultStore)

    # ══════════════════════════════════════════════════════════════════════
    # 2. LLM ADAPTERS
    # ══════════════════════════════════════════════════════════════════════
    # Core adapters (always available)
    from xulcan.llm.adapters.gemini import GeminiAdapter
    from xulcan.llm.adapters.openai_protocol import OpenAICompatibleAdapter
    from xulcan.llm.adapters.ollama import OllamaAdapter
    from xulcan.llm.adapters.groq import GroqAdapter
    from xulcan.llm.adapters.github import GitHubModelsAdapter
    from xulcan.llm.adapters.sambanova import SambaNovaAdapter

    container.llm.register("gemini", GeminiAdapter)
    container.llm.register("openai", OpenAICompatibleAdapter)
    container.llm.register("ollama", OllamaAdapter)
    container.llm.register("groq", GroqAdapter)
    container.llm.register("github", GitHubModelsAdapter)
    container.llm.register("sambanova", SambaNovaAdapter)

    # Optional adapters (conditionally registered if dependencies available)
    _register_optional_llm_adapter(container, "anthropic", "xulcan.llm.adapters.anthropic", "AnthropicAdapter")
    _register_optional_llm_adapter(container, "mistral", "xulcan.llm.adapters.mistral", "MistralAdapter")
    _register_optional_llm_adapter(container, "cohere", "xulcan.llm.adapters.cohere", "CohereAdapter")
    _register_optional_llm_adapter(container, "deepseek", "xulcan.llm.adapters.deepseek", "DeepSeekAdapter")
    _register_optional_llm_adapter(container, "huggingface", "xulcan.llm.adapters.huggingface", "HuggingFaceAdapter")

    # ══════════════════════════════════════════════════════════════════════
    # 3. CONTEXT STRATEGIES
    # ══════════════════════════════════════════════════════════════════════

    from xulcan.context.strategies.full import FullHistoryStrategy
    from xulcan.context.strategies.sliding import SlidingWindowStrategy

    container.context.register("full_history", FullHistoryStrategy)
    container.context.register("sliding_window", SlidingWindowStrategy)

    # ══════════════════════════════════════════════════════════════════════
    # 4. BURSAR STRATEGIES
    # ══════════════════════════════════════════════════════════════════════

    from xulcan.governance.bursar.strategies.unlimited import UnlimitedBursarStrategy
    from xulcan.governance.bursar.strategies.enforced import EnforcedBursarStrategy

    container.bursar.register("unlimited", UnlimitedBursarStrategy)
    container.bursar.register("enforced", EnforcedBursarStrategy)

    # ══════════════════════════════════════════════════════════════════════
    # 5. SENTINEL STRATEGIES
    # ══════════════════════════════════════════════════════════════════════

    from xulcan.governance.sentinel.strategies.passthrough import PassthroughSentinelStrategy
    from xulcan.governance.sentinel.strategies.blocklist import BlocklistSentinelStrategy

    container.sentinel.register("passthrough", PassthroughSentinelStrategy)
    container.sentinel.register("blocklist", BlocklistSentinelStrategy)

    # ══════════════════════════════════════════════════════════════════════
    # 6. HUMAN GATE STRATEGIES
    # ══════════════════════════════════════════════════════════════════════

    from xulcan.governance.human.strategies.auto import AutoApproveHumanGateStrategy
    from xulcan.governance.human.strategies.terminal import TerminalHumanGateStrategy
    from xulcan.governance.human.strategies.api import ApiHumanGateStrategy

    container.human_gate.register("auto_approve", AutoApproveHumanGateStrategy)
    container.human_gate.register("terminal", TerminalHumanGateStrategy)
    container.human_gate.register("api", ApiHumanGateStrategy)


def _register_optional_llm_adapter(
    container: RegistryContainer,
    adapter_name: str,
    module_path: str,
    class_name: str,
) -> None:
    """Conditionally register an LLM adapter if its dependencies are available.

    Args:
        container: The RegistryContainer to register into.
        adapter_name: The name to register the adapter under (e.g., "anthropic").
        module_path: The full module path (e.g., "xulcan.llm.adapters.anthropic").
        class_name: The class name within that module (e.g., "AnthropicAdapter").
    """
    try:
        import importlib
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        container.llm.register(adapter_name, adapter_class)
        logger.debug(f"✓ Registered LLM adapter: {adapter_name}")
    except (ImportError, AttributeError) as e:
        logger.debug(f"⊘ Skipped optional LLM adapter '{adapter_name}': {type(e).__name__}")

