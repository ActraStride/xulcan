from __future__ import annotations

import importlib.util
import inspect
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from xulcan.runtime.loaders.blueprint_loader import BlueprintLoader

if TYPE_CHECKING:
    from xulcan.app import Xulcan

logger = logging.getLogger("xulcan.runtime.loaders.app_discovery")


class AppDiscoveryEngine:
    """Discovers apps from disk and registers namespaces, agents, and tools."""

    def __init__(self, client: Xulcan):
        self._client = client

    async def discover_all(self, app_paths: list[str], base_dir: str | None = None) -> None:
        if not app_paths:
            return

        base_dir_path = Path(base_dir) if base_dir else Path.cwd()
        resolved_paths = [
            Path(path) if Path(path).is_absolute() else base_dir_path / path
            for path in app_paths
        ]

        for path in resolved_paths:
            await self._discover_app(path)

    async def _discover_app(self, app_root: Path) -> None:
        app_root = app_root.resolve()
        if not app_root.exists():
            raise FileNotFoundError(f"App folder not found: {app_root}")
        if not app_root.is_dir():
            raise ValueError(f"App path is not a directory: {app_root}")

        namespace = app_root.name
        logger.info("📦 Discovering app namespace '%s' at %s", namespace, app_root)

        blueprint_files = self._collect_blueprint_files(app_root)
        tool_files = self._collect_tool_files(app_root / "tools")

        if not blueprint_files and not tool_files:
            raise ValueError(
                f"App folder '{app_root}' must contain at least one agent YAML or one tool Python file."
            )

        for blueprint_path in blueprint_files:
            blueprint = self._load_blueprint(blueprint_path, namespace, app_root)
            self._register_blueprint(blueprint)

        for tool_path in tool_files:
            self._load_tool_file(tool_path, namespace, app_root / "tools")

    def _collect_blueprint_files(self, app_root: Path) -> list[Path]:
        patterns = ["*.xul.yml", "*.xul.yaml", "*.yml", "*.yaml"]
        files: list[Path] = []
        for pattern in patterns:
            for file_path in app_root.rglob(pattern):
                if "tools" in file_path.parts:
                    continue
                files.append(file_path)
        files.sort()
        return files

    def _collect_tool_files(self, tools_root: Path) -> list[Path]:
        if not tools_root.exists() or not tools_root.is_dir():
            return []

        return sorted(
            [path for path in tools_root.rglob("*.py") if path.name != "__init__.py"],
            key=lambda p: str(p)
        )

    def _load_blueprint(self, blueprint_path: Path, namespace: str, app_root: Path) -> Any:
        derived_id = self._derive_agent_id(namespace, blueprint_path, app_root)
        raw_data = yaml.safe_load(blueprint_path.read_text(encoding="utf-8"))

        if not raw_data:
            raise ValueError(f"Blueprint file is empty: {blueprint_path}")

        if not isinstance(raw_data, dict):
            raise ValueError(f"Invalid blueprint content in {blueprint_path}. Expected a YAML mapping.")

        if not raw_data.get("id"):
            raw_data["id"] = derived_id
        elif raw_data["id"] != derived_id:
            raise ValueError(
                f"Blueprint ID mismatch for '{blueprint_path}': declared id '{raw_data['id']}' "
                f"does not match inferred app id '{derived_id}'."
            )

        blueprint = BlueprintLoader.from_dict(raw_data)
        return blueprint

    def _register_blueprint(self, blueprint: Any) -> None:
        if blueprint.id in self._client.agent_registry:
            raise ValueError(
                f"Duplicate agent id '{blueprint.id}' discovered while loading apps."
            )
        self._client.agent_registry[blueprint.id] = blueprint
        logger.info("✅ App blueprint registered: %s", blueprint.id)

    def _load_tool_file(self, tool_path: Path, namespace: str, tools_root: Path) -> None:
        module = self._import_python_module(tool_path, namespace, tools_root)
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or func.__module__ != module.__name__:
                continue
            logger.info("🔧 Registering tool '%s' under namespace '%s'", name, namespace)
            self._client.tool(namespace=namespace)(func)

    def _import_python_module(self, tool_path: Path, namespace: str, tools_root: Path) -> Any:
        module_name = self._tool_module_name(tool_path, namespace, tools_root)
        spec = importlib.util.spec_from_file_location(module_name, tool_path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not import tool module from {tool_path}")

        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _tool_module_name(tool_path: Path, namespace: str, tools_root: Path) -> str:
        sanitized = tool_path.with_suffix("").relative_to(tools_root)
        module_fragment = sanitized.as_posix().replace("/", ".")
        unique_id = uuid.uuid4().hex[:8]
        return f"xulcan_app_discovery.{namespace}.{module_fragment}.{unique_id}"

    def _derive_agent_id(self, namespace: str, blueprint_path: Path, app_root: Path) -> str:
        relative = blueprint_path.relative_to(app_root)
        filename = relative.name
        if filename in {"main.xul.yml", "main.xul.yaml", "main.yml", "main.yaml"}:
            rel_parts = relative.with_suffix("").with_suffix("").parts
            if len(rel_parts) <= 1:
                return namespace
            return f"{namespace}.{'.'.join(rel_parts[:-1])}"

        stem = self._strip_blueprint_suffix(relative.name)
        path_parts = list(relative.parent.parts) if relative.parent.parts else []
        path_parts.append(stem)
        return f"{namespace}.{'.'.join(path_parts)}" if path_parts else namespace

    @staticmethod
    def _strip_blueprint_suffix(filename: str) -> str:
        if filename.endswith(".xul.yml"):
            return filename[: -len(".xul.yml")]
        if filename.endswith(".xul.yaml"):
            return filename[: -len(".xul.yaml")]
        if filename.endswith(".yml"):
            return filename[: -len(".yml")]
        if filename.endswith(".yaml"):
            return filename[: -len(".yaml")]
        return Path(filename).stem
