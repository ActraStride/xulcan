import asyncio
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

from xulcan.app import Xulcan
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.manifest.schema import InfraprintManifest
from xulcan.kernel.orchestrator import ProtoKernel


def test_manifest_accepts_apps_list() -> None:
    manifest = InfraprintManifest.model_validate({
        "version": "1.0.0",
        "kernel": {"vault": {"driver": "memory"}},
        "providers": {
            "llm": {
                "default": "gemini",
                "instances": {
                    "gemini": {"driver": "gemini", "model": "test"}
                }
            }
        },
        "blueprints": {"paths": [], "autoload": False},
        "apps": ["apps/chat", "apps/quotations"],
    })

    assert manifest.apps == ["apps/chat", "apps/quotations"]


def make_blueprint_yaml(name: str, system_prompt: str) -> str:
    return textwrap.dedent(
        """
        xulcan_version: "2.0"
        name: "%s"
        model: gemini/test
        system_prompt: "%s"
        tools: []
        """
    ) % (name, system_prompt)


def test_app_discovery_registers_app_namespace_and_tools(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    chat_app = apps_dir / "chat"
    quotations_app = apps_dir / "quotations"
    (chat_app / "tools").mkdir(parents=True)
    (quotations_app / "tools").mkdir(parents=True)

    (chat_app / "main.xul.yml").write_text(make_blueprint_yaml("Chat", "Hello"), encoding="utf-8")
    (chat_app / "tools" / "history.py").write_text(
        "def history():\n    return 'history'\n",
        encoding="utf-8",
    )

    (quotations_app / "main.xul.yml").write_text(make_blueprint_yaml("Quotations", "Hello"), encoding="utf-8")
    (quotations_app / "validator.xul.yml").write_text(make_blueprint_yaml("Validator", "Validate"), encoding="utf-8")
    (quotations_app / "tools" / "database.py").write_text(
        "def database():\n    return 'database'\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "Xulcanfile"
    manifest_path.write_text(
        textwrap.dedent(
            """
            version: "1.0.0"
            kernel:
              vault:
                driver: memory
            providers:
              llm:
                default: gemini
                instances:
                  gemini:
                    driver: gemini
                    model: test
            blueprints:
              paths: []
              autoload: false
            apps:
              - apps/chat
              - apps/quotations
            """
        ),
        encoding="utf-8",
    )

    client = asyncio.run(Xulcan.from_manifest(str(manifest_path)))
    tool_router = cast(Any, client.runtime.tool_router)

    assert "chat" in client.agent_registry
    assert "quotations" in client.agent_registry
    assert "quotations.validator" in client.agent_registry
    assert "chat.history" in tool_router._routing_table
    assert "quotations.database" in tool_router._routing_table
    assert tool_router._llm_name_index["chat__history"] == "chat.history"
    assert tool_router._llm_name_index["quotations__database"] == "quotations.database"


def test_app_folder_without_agents_or_tools_raises(tmp_path: Path) -> None:
    empty_app = tmp_path / "apps" / "empty"
    empty_app.mkdir(parents=True)

    manifest_path = tmp_path / "Xulcanfile"
    manifest_path.write_text(
        textwrap.dedent(
            """
            version: "1.0.0"
            kernel:
              vault:
                driver: memory
            providers:
              llm:
                default: gemini
                instances:
                  gemini:
                    driver: gemini
                    model: test
            blueprints:
              paths: []
              autoload: false
            apps:
              - apps/empty
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain at least one agent YAML or one tool Python file"):
        asyncio.run(Xulcan.from_manifest(str(manifest_path)))


def test_tool_name_collision_is_namespaced(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    chat_app = apps_dir / "chat"
    quotations_app = apps_dir / "quotations"
    (chat_app / "tools").mkdir(parents=True)
    (quotations_app / "tools").mkdir(parents=True)

    (chat_app / "main.xul.yml").write_text(make_blueprint_yaml("Chat", "Hello"), encoding="utf-8")
    (chat_app / "tools" / "save.py").write_text("def save():\n    return 'chat'\n", encoding="utf-8")

    (quotations_app / "main.xul.yml").write_text(make_blueprint_yaml("Quotations", "Hello"), encoding="utf-8")
    (quotations_app / "tools" / "save.py").write_text("def save():\n    return 'quotations'\n", encoding="utf-8")

    manifest_path = tmp_path / "Xulcanfile"
    manifest_path.write_text(
        textwrap.dedent(
            """
            version: "1.0.0"
            kernel:
              vault:
                driver: memory
            providers:
              llm:
                default: gemini
                instances:
                  gemini:
                    driver: gemini
                    model: test
            blueprints:
              paths: []
              autoload: false
            apps:
              - apps/chat
              - apps/quotations
            """
        ),
        encoding="utf-8",
    )

    client = asyncio.run(Xulcan.from_manifest(str(manifest_path)))
    tool_router = cast(Any, client.runtime.tool_router)

    assert "chat.save" in tool_router._routing_table
    assert "quotations.save" in tool_router._routing_table
    assert tool_router._llm_name_index["chat__save"] == "chat.save"
    assert tool_router._llm_name_index["quotations__save"] == "quotations.save"


def test_kernel_resolves_short_names_to_namespace() -> None:
    blueprint = AgentBlueprint.model_validate({
        "xulcan_version": "2.0",
        "id": "chat.main",
        "name": "Chat Main",
        "model": "gemini/test",
        "system_prompt": "Hello",
        "tools": [],
    })
    kernel = cast(Any, object.__new__(ProtoKernel))

    resolved = kernel._resolve_tool_names(blueprint, ["analyzer"])

    assert resolved == ["chat__analyzer"]
