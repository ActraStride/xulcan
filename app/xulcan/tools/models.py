"""Model registry and model-as-tool helpers."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel

from .base import BaseTool
from .registry import ToolRegistry


class ModelSpec(BaseModel):
    """Model specification for orchestration."""

    model_config = {"protected_namespaces": ()}

    name: str
    provider: Literal["openai", "openrouter", "anthropic", "gemini", "zai", "deepseek"]
    model_id: str
    system_prompt: Optional[str] = None
    tools: List[str] = []
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


class ModelRegistry:
    """Registry of available LLM models."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelSpec] = {}

    def register(self, model: ModelSpec) -> None:
        if model.name in self._models:
            raise ValueError(f"Model '{model.name}' is already registered")
        self._models[model.name] = model

    def get(self, name: str) -> Optional[ModelSpec]:
        return self._models.get(name)

    def list(self) -> List[str]:
        return list(self._models.keys())


class ModelTool(BaseTool):
    """Expose a model invocation as a tool for orchestration."""

    model: str
    prompt: str
    tool_subset: Optional[List[str]] = None

    _model_registry: ClassVar[Optional[ModelRegistry]] = None
    _tool_registry: ClassVar[Optional[ToolRegistry]] = None
    _client_factory: ClassVar[Optional[Any]] = None
    _adapters: ClassVar[Dict[str, Any]] = {}

    @classmethod
    def configure(
        cls,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        client_factory: Any,
        adapters: Dict[str, Any],
    ) -> None:
        cls._model_registry = model_registry
        cls._tool_registry = tool_registry
        cls._client_factory = client_factory
        cls._adapters = adapters

    async def run(self) -> Dict[str, Any]:
        if not self._model_registry or not self._client_factory:
            raise RuntimeError("ModelTool is not configured")

        spec = self._model_registry.get(self.model)
        if not spec:
            raise ValueError(f"Unknown model: {self.model}")

        client = self._client_factory.get_client(spec.provider)
        adapter = self._adapters.get(spec.provider)

        messages: List[Dict[str, Any]] = []
        if spec.system_prompt:
            messages.append({"role": "system", "content": spec.system_prompt})
        messages.append({"role": "user", "content": self.prompt})

        tools = []
        if adapter and self._tool_registry:
            if self.tool_subset:
                subset_registry = ToolRegistry()
                for name in self.tool_subset:
                    tool_cls = self._tool_registry.get(name)
                    if tool_cls:
                        subset_registry.register(tool_cls)
                tools = adapter.export_tools(subset_registry)
            elif spec.tools:
                subset_registry = ToolRegistry()
                for name in spec.tools:
                    tool_cls = self._tool_registry.get(name)
                    if tool_cls:
                        subset_registry.register(tool_cls)
                tools = adapter.export_tools(subset_registry)

        response = await client.create_chat_completion(
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            model=spec.model_id,
        )

        return {
            "model": spec.name,
            "provider": spec.provider,
            "output": response.content,
            "tool_calls": response.tool_calls,
        }
