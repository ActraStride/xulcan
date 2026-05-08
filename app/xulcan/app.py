"""Xulcan OS — The Core Application Facade (DEFINITIVE VERSION).

Acts as the IoC Container / Assembler for the entire Xulcan ecosystem.
This is the only place in the system that knows about concrete implementations.

FIXED ISSUES:
    - BaseLLMAdapter → LLMProvider (correct interface name)
    - Proper credential handling
    - Consistent registry usage
    - Issue 23: Registry instantiation now delegated to RegistryContainer + bootstrap_registries

Separation of concerns:
    registry/bootstrap.py knows: WHICH built-in adapters exist
    app.py knows:               WHERE credentials come from, HOW to wire them
    Blueprint knows:            HOW the agent thinks, WHAT tools it has
    Kernel knows:               HOW to drive the FSM loop
"""

from __future__ import annotations

import os
import logging
import inspect
import types
import functools
import glob
from collections.abc import Callable
from typing import Any, get_origin, get_args, AsyncIterator

from xulcan.kernel.interfaces import (
    LLMProvider, LLMOrchestrator, LedgerRepository, StateStore,
    ContextStrategy, BursarStrategy, SentinelStrategy, HumanGateStrategy, EventBus
)

# ── System factories ──
from xulcan.registry import ProviderRegistry, CredentialProxy, RegistryContainer, bootstrap_registries
from xulcan.system.loader import BlueprintLoader
from xulcan.kernel.runtime import ProtoKernel
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.protocol.tools import ToolDefinition, FunctionDef
from xulcan.kernel.environment import SystemEnvironment

# ── Adapters (Classes, not instances) ──
from xulcan.memory.vault.adapters.in_memory import MemoryVaultStore
from xulcan.llm.executor import LLMExecutor

# ── Executors ──
from xulcan.tools.router import ToolRouterExecutor
from xulcan.tools.executors.local import LocalPythonExecutor
from xulcan.tools.executors.agent import SubAgentExecutor
from xulcan.tools.executors.sandbox.docker import DockerProvider
from xulcan.tools.executors.sandbox.executor import SandboxExecutor

logger = logging.getLogger("xulcan.app")


class Xulcan:
    """Xulcan Agent OS — Facade and IoC Container."""

    def __init__(
        self,
        gemini_api_key: str | None = None,
        groq_api_key: str | None = None,
        ollama_host: str = "http://ollama:11434",
        anthropic_api_key: str | None = None,
        sambanova_api_key: str | None = None,
        github_token: str | None = None,
        tool_secrets: dict[str, dict[str, Any]] | None = None,
    ):
        self.agent_registry: dict[str, AgentBlueprint] = {}

        # ══════════════════════════════════════════════════════════════════
        # 1. REGISTRIES (Abstract Factories via RegistryContainer)
        # ══════════════════════════════════════════════════════════════════
        # Issue 23: Delegate all registry instantiation and bootstrap to
        # RegistryContainer + bootstrap_registries(). This is the only place
        # in app.py that interacts with raw registries.
        self.registries = RegistryContainer()
        bootstrap_registries(self.registries)

        # Maintain attribute aliases for backward compatibility with kernel
        # and other components that expect these as top-level attributes
        self.ledger_registry = self.registries.ledger
        self.store_registry = self.registries.state_store
        self.bus_registry = self.registries.event_bus
        self.context_registry = self.registries.context
        self.bursar_registry = self.registries.bursar
        self.sentinel_registry = self.registries.sentinel
        self.human_gate_registry = self.registries.human_gate

        # ══════════════════════════════════════════════════════════════════
        # 2. CREDENTIALS & ORCHESTRATOR
        # ══════════════════════════════════════════════════════════════════
        llm_secrets = {
            "gemini": {"api_key": gemini_api_key or os.getenv("GEMINI_API_KEY")},
            "groq": {"api_key": groq_api_key or os.getenv("GROQ_API_KEY")},
            "ollama": {"host": ollama_host},
            "anthropic": {"api_key": anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")},
            "sambanova": {"api_key": sambanova_api_key or os.getenv("SAMBANOVA_API_KEY")},
            "github": {"api_key": github_token or os.getenv("GITHUB_TOKEN")},
        }

        from xulcan.registry import ToolSecretsVault
        self.tool_vault = ToolSecretsVault(tool_secrets or {})

        # The CredentialProxy protects both LLM adapters and tool credentials
        self.llm_registry = CredentialProxy(
            self.registries.llm,
            llm_secrets,
            tool_vault=self.tool_vault
        )

        # Cognitive Orchestrator (handles caching and fallbacks)
        self.llm_executor = LLMExecutor(registry=self.llm_registry)

        # ══════════════════════════════════════════════════════════════════
        # 3. ACTIVE INFRASTRUCTURE (Instances & Wiring)
        # ══════════════════════════════════════════════════════════════════
        self.event_bus = self.bus_registry.build("memory", {})
        self.active_ledger = self.ledger_registry.build("memory", {"event_bus": self.event_bus})
        self.state_store = self.store_registry.build("memory", {})
        self.vault_store = MemoryVaultStore()

        self.environment = SystemEnvironment(
            state_store=self.state_store,
            vault_store=self.vault_store,
            event_bus=self.event_bus,
            workspace_id=None
        )

        # ══════════════════════════════════════════════════════════════════
        # 4. TOOL LAYER (Muscles)
        # ══════════════════════════════════════════════════════════════════
        self.local_tools = LocalPythonExecutor(environment=self.environment)
        self.sub_agent_tools = SubAgentExecutor(environment=self.environment)
        self.tool_router = ToolRouterExecutor(environment=self.environment)

        self.sandbox_executor: SandboxExecutor | None = None
        try:
            self.sandbox_executor = SandboxExecutor(
                provider=DockerProvider(),
                environment=self.environment
            )
        except Exception:
            logger.warning("⚠️ Docker unavailable. Sandbox tools disabled.")

        # ══════════════════════════════════════════════════════════════════
        # 5. KERNEL (Brain)
        # ══════════════════════════════════════════════════════════════════
        self.kernel = ProtoKernel(
            repository=self.active_ledger,
            llm_executor=self.llm_executor,
            tool_executor=self.tool_router,
            context_registry=self.context_registry,
            bursar_registry=self.bursar_registry,
            sentinel_registry=self.sentinel_registry,
            human_gate_registry=self.human_gate_registry,
            environment=self.environment,
        )

        self.sub_agent_tools.bind_kernel(self.kernel)

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC API (Developer Experience)
    # ══════════════════════════════════════════════════════════════════════

    def load_blueprints_from_dir(self, directory: str = "blueprints") -> int:
        """Load all YAML files from a directory atomically."""
        import os
        new_registry: dict[str, AgentBlueprint] = {}
        if not os.path.exists(directory):
            os.makedirs(directory)

        yaml_files = glob.glob(f"{directory}/*.yaml") + glob.glob(f"{directory}/*.yml")
        for file_path in yaml_files:
            try:
                bp = BlueprintLoader.from_file(file_path)
                if bp.id not in new_registry:
                    new_registry[bp.id] = bp
            except Exception as e:
                logger.error(f"❌ YAML broken ignored ({file_path}): {e}")

        self.agent_registry = new_registry
        return len(new_registry)

    def load_agent(self, source: Any) -> AgentBlueprint:
        """Load an agent from a dict, YAML string, or .yml file path."""
        if isinstance(source, dict):
            return BlueprintLoader.from_dict(source)
        elif isinstance(source, str):
            if source.endswith((".yml", ".yaml")):
                return BlueprintLoader.from_file(source)
            return BlueprintLoader.from_yaml_string(source)
        raise TypeError("Source must be a dict, YAML string, or .yml file path.")

    def tool(
        self,
        _func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None
    ) -> Callable[..., Any]:
        """Decorator: converts Python functions into agentic tools."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            tool_desc = description or inspect.getdoc(func) or "No description provided."

            sig = inspect.signature(func)
            properties: dict[str, Any] = {}
            required: list[str] = []

            INJECTED = {"context", "self", "run_id", "state_store", "environment"}

            for param_name, param in sig.parameters.items():
                if param_name in INJECTED:
                    continue

                param_type = param.annotation
                origin = get_origin(param_type)

                # Handles both Python 3.9 typing.Union and Python 3.10+ types.UnionType
                import typing
                if origin is typing.Union or origin is types.UnionType:
                    inner = [a for a in get_args(param_type) if a is not type(None)]
                    param_type = inner[0] if inner else str

                json_type = "string"
                if param_type is int:
                    json_type = "integer"
                elif param_type is float:
                    json_type = "number"
                elif param_type is bool:
                    json_type = "boolean"
                elif param_type is list or get_origin(param_type) is list:
                    json_type = "array"
                elif param_type is dict or get_origin(param_type) is dict:
                    json_type = "object"

                properties[param_name] = {
                    "type": json_type,
                    "description": f"Parameter: {param_name}"
                }

                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            definition = ToolDefinition(
                type="function",
                function=FunctionDef(
                    name=tool_name,
                    description=tool_desc.strip(),
                    parameters={"type": "object", "properties": properties, "required": required}
                )
            )
            self._add_tool(definition, func)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return wrapper

        if _func is None:
            return decorator
        return decorator(_func)

    def add_agent(self, blueprint: AgentBlueprint, description: str) -> str:
        """Register a sub-agent as a tool. Returns the tool name."""
        tool_name = blueprint.id.replace("-", "_")
        definition = ToolDefinition(
            type="function",
            function=FunctionDef(
                name=tool_name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Detailed instructions."},
                        "output_memory_key": {"type": "string", "description": "Optional RAM key."}
                    },
                    "required": ["prompt"]
                }
            )
        )
        self._add_tool(definition, blueprint)
        return tool_name

    def enable_sandbox(self) -> list[str]:
        """Activates Docker sandbox tools. Returns list of exposed tool names."""
        if not self.sandbox_executor:
            raise RuntimeError("Docker Sandbox not available on this machine.")

        tools = [
            ToolDefinition(type="function", function=FunctionDef(
                name="sandbox_run_python",
                description="Executes Python code safely in an ephemeral container.",
                parameters={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
            )),
            ToolDefinition(type="function", function=FunctionDef(
                name="sandbox_run_bash",
                description="Executes bash commands in the sandbox terminal.",
                parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
            )),
            ToolDefinition(type="function", function=FunctionDef(
                name="sandbox_write_file",
                description="Writes a file to the sandbox persistent disk.",
                parameters={"type": "object", "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"}
                }, "required": ["file_path", "content"]}
            )),
            ToolDefinition(type="function", function=FunctionDef(
                name="sandbox_read_file",
                description="Reads a file from the sandbox container.",
                parameters={"type": "object", "properties": {
                    "file_path": {"type": "string"}
                }, "required": ["file_path"]}
            )),
        ]
        for t in tools:
            self._add_tool(t, "sandbox")
        return [t.function.name for t in tools]

    def enable_stdlib(self, modules: list[str] | str = "all") -> list[str]:
        """Activates Xulcan stdlib tool packages. Returns list of enabled tool names."""
        if modules == "all":
            modules = ["fs", "network"]
        elif isinstance(modules, str):
            modules = [modules]

        enabled: list[str] = []

        if "fs" in modules:
            from xulcan.tools.stdlib.fs import list_directory, read_file_content, read_file_ast
            self.tool(description="Lists a local directory")(list_directory)
            self.tool(description="Reads the content of a local file")(read_file_content)
            self.tool(description="Reads the AST of a Python file")(read_file_ast)
            enabled.extend(["list_directory", "read_file_content", "read_file_ast"])

        if "network" in modules:
            from xulcan.tools.stdlib.network import network_fetch_webpage, network_api_get
            self.tool(description="Downloads and cleans a webpage")(network_fetch_webpage)
            self.tool(description="Makes a GET request to a REST API")(network_api_get)
            enabled.extend(["network_fetch_webpage", "network_api_get"])

        logger.info("📦 Xulcan Stdlib loaded: %s", ', '.join(modules))
        return enabled

    async def run(
        self,
        prompt: str,
        agent_id: str,
        blueprint: AgentBlueprint | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[str, str]:

        if not blueprint:
            raise ValueError("An AgentBlueprint must be provided to run.")

        parent_id = None
        if session_key:
            parent_id = await self.active_ledger.get_last_run_id(session_key)

        actual_run_id, response = await self.kernel.execute_run(
            blueprint=blueprint,
            user_input=prompt,
            agent_id=agent_id,
            parent_id=parent_id,
            run_id=run_id,
            metadata=metadata
        )

        if session_key:
            await self.active_ledger.tag_run(actual_run_id, session_key)

        response_text = str(response.content) if response and response.content else ""
        return actual_run_id, response_text

    async def get_audit(self, run_id: str) -> dict[str, Any]:
        """Returns the full event ledger (black box) for a run."""
        try:
            summary = await self.active_ledger.get_summary(run_id)
            events = await self.active_ledger.get_events(run_id)
            return {
                "summary": summary.model_dump(mode='json') if summary else None,
                "history": [e.model_dump(mode='json') for e in events]
            }
        except KeyError:
            return {"error": f"Run {run_id} not found."}

    def subscribe_to_firehose(self, run_id: str) -> AsyncIterator[str]:
        """Returns an async iterator for real-time Firehose events."""
        channel = f"xulcan:firehose:{run_id}"
        return self.event_bus.subscribe(channel)

    def subscribe_to_ipc(self, run_id: str) -> AsyncIterator[str]:
        """Listens to internal communications and tool progress bars."""
        channel = f"xulcan:ipc:{run_id}"
        return self.event_bus.subscribe(channel)

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE
    # ══════════════════════════════════════════════════════════════════════

    def _add_tool(self, definition: ToolDefinition, target: Any) -> None:
        """Low-level router. Use @tool, add_agent, or enable_sandbox instead."""
        if isinstance(target, AgentBlueprint):
            self.sub_agent_tools.register_agent(definition, target)
            self.tool_router.route_tool(definition.function.name, self.sub_agent_tools)
        elif callable(target):
            self.local_tools.register_function(definition, target)
            self.tool_router.route_tool(definition.function.name, self.local_tools)
        elif target == "sandbox":
            assert self.sandbox_executor is not None, "Sandbox executor is not initialized."
            self.sandbox_executor.register_tool(definition)
            self.tool_router.route_tool(definition.function.name, self.sandbox_executor)
