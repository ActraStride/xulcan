"""Xulcan OS — The Core Application Facade (DEFINITIVE VERSION).

Acts as the runtime-native facade over RuntimeContext.
Public API surface only; runtime construction is delegated to the
materialization and assembly pipeline.

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

# ── System factories ──
from xulcan.registry import RegistryContainer, bootstrap_registries
from xulcan.runtime.loaders import AppDiscoveryEngine, BlueprintLoader
from xulcan.kernel.orchestrator import ProtoKernel
from xulcan.runtime import ManifestResolver, RuntimeAssembler, RuntimeContext
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.protocol.tools import ToolDefinition, FunctionDef

logger = logging.getLogger("xulcan.app")


class Xulcan:
    """Xulcan Agent OS — Facade over an assembled RuntimeContext.

    This class delegates execution and observability to RuntimeContext.
    It does not construct infrastructure directly.
    """

    def __init__(self, runtime: RuntimeContext):
        self._runtime = runtime
        self.agent_registry: dict[str, AgentBlueprint] = {}
        self._registries: RegistryContainer | None = None

    @classmethod
    async def from_manifest(cls, manifest_path: str = "Xulcanfile") -> "Xulcan":
        container = RegistryContainer()
        bootstrap_registries(container)

        resolver = ManifestResolver(container)
        infrastructure = await resolver.load(manifest_path)

        assembler = RuntimeAssembler(infrastructure, container)
        runtime = await assembler.assemble()

        instance = cls(runtime)
        instance._registries = container

        # ── Autodiscover apps from the manifest if configured ────────────
        app_paths = infrastructure.manifest.apps if hasattr(infrastructure.manifest, 'apps') else []
        if app_paths:
            manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
            discovery_engine = AppDiscoveryEngine(instance)
            await discovery_engine.discover_all(app_paths, base_dir=manifest_dir)

        # ── Autoload blueprints si el manifest lo indica ──────────────────
        bp_config = runtime.infrastructure.manifest.blueprints
        if bp_config.autoload:
            manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
            logger.info(
                "📂 Autoloading blueprints from %d path(s): %s",
                len(bp_config.paths),
                bp_config.paths,
            )
            for path in bp_config.paths:
                resolved = os.path.join(manifest_dir, path)
                instance.load_blueprints_from_dir(resolved)

        return instance

    @property
    def runtime(self) -> RuntimeContext:
        return self._runtime

    @property
    def kernel(self) -> ProtoKernel:
        return self._runtime.kernel

    @property
    def infrastructure(self):
        return self._runtime.infrastructure

    @property
    def event_bus(self):
        return self._runtime.infrastructure.event_bus

    @property
    def active_ledger(self):
        return self._runtime.infrastructure.ledger

    @property
    def environment(self):
        return self._runtime.environment

    @property
    def tool_router(self):
        return self._runtime.tool_router

    @property
    def local_tools(self):
        return self._runtime.local_executor

    @property
    def sub_agent_tools(self):
        return self._runtime.sub_agent_executor

    @property
    def sandbox_executor(self):
        return self._runtime.sandbox_executor

    @property
    def registries(self) -> RegistryContainer | None:
        return self._registries

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC API (Developer Experience)
    # ══════════════════════════════════════════════════════════════════════

    def load_blueprints_from_dir(self, directory: str = "blueprints") -> int:
        """Load all YAML files from a directory atomically."""
        import os
        new_registry: dict[str, AgentBlueprint] = {}
        if not os.path.exists(directory):
            os.makedirs(directory)

        yaml_files = (
            glob.glob(f"{directory}/*.yaml")
            + glob.glob(f"{directory}/*.yml")
            + glob.glob(f"{directory}/*.xul.yml")
            + glob.glob(f"{directory}/*.xul.yaml")
        )
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
        description: str | None = None,
        namespace: str | None = None
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
            self._add_tool(definition, func, namespace)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return wrapper

        if _func is None:
            return decorator
        return decorator(_func)

    def add_agent(self, blueprint: AgentBlueprint, description: str, namespace: str | None = None) -> str:
        """Register a sub-agent as a tool. Returns the tool name."""
        # Use blueprint ID (sanitizing dashes to underscores) as default namespace
        effective_namespace = namespace or blueprint.id.replace("-", "_")
        tool_name = "run"  # Canonical base name for sub-agents
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
        self._add_tool(definition, blueprint, effective_namespace)
        return f"{effective_namespace}__{tool_name}"

    def enable_sandbox(self) -> list[str]:
        """Activates Docker sandbox tools. Returns list of exposed tool names."""
        if not self._runtime.sandbox_executor:
            logger.warning("⚠️ Sandbox executor not available. Sandbox tools are disabled.")
            return []

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
            self._add_tool(t, "sandbox", None)
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
        app_config: "AppConfig | None" = None,  # ← Issue #52: App-level governance
    ) -> tuple[str, str]:

        if not blueprint:
            raise ValueError("An AgentBlueprint must be provided to run.")

        # ── Issue #52: Resolve AppConfig if not provided ───────────────
        # If app_config is not passed, try to resolve it from the manifest
        # based on the blueprint's namespace.
        if app_config is None and self._runtime.infrastructure.manifest.apps:
            app_config = self._resolve_app_for_blueprint(
                blueprint, self._runtime.infrastructure.manifest.apps
            )

        parent_id = None
        if session_key:
            parent_id = await self.active_ledger.get_last_run_id(session_key)

        actual_run_id, response = await self._runtime.kernel.execute_run(
            blueprint=blueprint,
            user_input=prompt,
            agent_id=agent_id,
            app_config=app_config,  # ← Issue #52: Pass AppConfig for hierarchical governance
            parent_id=parent_id,
            run_id=run_id,
            metadata=metadata
        )

        if session_key:
            await self.active_ledger.tag_run(actual_run_id, session_key)

        response_text = str(response.content) if response and response.content else ""
        return actual_run_id, response_text

    def _resolve_app_for_blueprint(
        self,
        blueprint: AgentBlueprint,
        apps: list["AppConfig"],
    ) -> "AppConfig | None":
        """Resolve which AppConfig a blueprint belongs to based on namespace.

        The blueprint's ID (e.g., 'sales.pricing-agent') determines which
        app folder it belongs to. Matches the prefix of the blueprint.id
        with the app's path.
        """
        if not apps:
            return None

        # Blueprint ID format: namespace.agent-name (e.g., 'sales.pricing-agent')
        # App path format: the folder name (e.g., 'sales')
        blueprint_parts = blueprint.id.split('.')
        if len(blueprint_parts) < 2:
            return None

        blueprint_namespace = blueprint_parts[0]

        for app in apps:
            # Normalize app path for comparison
            app_path = app.path.replace('/', '.').replace('\\', '.')
            if blueprint_namespace == app_path or blueprint_namespace.startswith(f"{app_path}."):
                return app

        return None

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
        return self._runtime.infrastructure.event_bus.subscribe(channel)

    def subscribe_to_ipc(self, run_id: str) -> AsyncIterator[str]:
        """Listens to internal communications and tool progress bars."""
        channel = f"xulcan:ipc:{run_id}"
        return self._runtime.environment.event_bus.subscribe(channel)

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE
    # ══════════════════════════════════════════════════════════════════════

    def _add_tool(self, definition: ToolDefinition, target: Any, namespace: str | None = None) -> None:
        """Low-level router. Use @tool, add_agent, or enable_sandbox instead."""
        base_name = definition.function.name

        if namespace:
            route_key = f"{namespace}.{base_name}"
            llm_name = f"{namespace}__{base_name}"
            # Update the ToolDefinition with the sanitized name for the LLM
            definition = definition.model_copy(
                update={"function": definition.function.model_copy(update={"name": llm_name})}
            )
        else:
            route_key = base_name
            llm_name = base_name

        if isinstance(target, AgentBlueprint):
            self._runtime.sub_agent_executor.register_agent(definition, target)
            self._runtime.tool_router.route_tool(route_key, llm_name, self._runtime.sub_agent_executor)
        elif callable(target):
            self._runtime.local_executor.register_function(definition, target)
            self._runtime.tool_router.route_tool(route_key, llm_name, self._runtime.local_executor)
        elif target == "sandbox":
            assert self._runtime.sandbox_executor is not None, "Sandbox executor is not initialized."
            self._runtime.sandbox_executor.register_tool(definition)
            self._runtime.tool_router.route_tool(route_key, llm_name, self._runtime.sandbox_executor)