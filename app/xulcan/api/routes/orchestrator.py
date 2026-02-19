"""Orchestration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from xulcan.api.schemas.orchestrator import (
    ModelSpecRequest,
    OrchestrateRequest,
    OrchestrateResponse,
)
from xulcan.config import Settings, get_settings
from xulcan.core.engine.orchestrator import LLMOrchestrator, OrchestratorConfig
from xulcan.core.engine.policies import OrchestrationPolicy
from xulcan.core.llm import (
    AnthropicAdapter,
    GeminiAdapter,
    LLMAuthenticationError,
    LLMClientFactory,
    OpenAIAdapter,
)
from xulcan.tools import ModelRegistry, ModelSpec, ModelTool, ToolRegistry
from xulcan.tools import stdlib as tool_stdlib


router = APIRouter(prefix="/orchestrate", tags=["orchestrator"])


def _build_registries(
    request: OrchestrateRequest,
) -> tuple[ToolRegistry, ModelRegistry]:
    tool_registry = ToolRegistry()
    model_registry = ModelRegistry()

    tool_registry.auto_discover(tool_stdlib)

    models: list[ModelSpecRequest] = request.models or []
    core_present = any(model.name == request.core_model for model in models)

    # Register additional models first
    for model in models:
        model_registry.register(
            ModelSpec(
                name=model.name,
                provider=model.provider,
                model_id=model.model_id,
                system_prompt=model.system_prompt,
                tools=model.tools,
                max_tokens=model.max_tokens,
                temperature=model.temperature,
            )
        )

    # Register core model if not provided explicitly
    if not core_present:
        model_registry.register(
            ModelSpec(
                name=request.core_model,
                provider=request.provider,
                model_id=request.core_model,
                system_prompt=request.system_prompt,
                tools=request.tools or [],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        )

    # Register model tool for sub-model orchestration
    tool_registry.register(ModelTool)

    if request.tools:
        for tool_name in tool_registry.list():
            if tool_name == ModelTool.get_name():
                continue
            if tool_name not in request.tools:
                tool_registry.unregister(tool_name)

    return tool_registry, model_registry


def _get_adapter(provider: str):
    if provider == "openai":
        return OpenAIAdapter()
    if provider == "openrouter":
        return OpenAIAdapter()
    if provider == "zai":
        return OpenAIAdapter()
    if provider == "anthropic":
        return AnthropicAdapter()
    if provider == "gemini":
        return GeminiAdapter()
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


@router.post("", response_model=OrchestrateResponse)
async def orchestrate(
    request: OrchestrateRequest,
    settings: Settings = Depends(get_settings),
) -> OrchestrateResponse:
    tool_registry, model_registry = _build_registries(request)
    adapter = _get_adapter(request.provider)

    client_factory = LLMClientFactory(settings)
    adapters = {
        "openai": OpenAIAdapter(),
        "openrouter": OpenAIAdapter(),
        "zai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "gemini": GeminiAdapter(),
    }

    ModelTool.configure(model_registry, tool_registry, client_factory, adapters)

    policy = (
        OrchestrationPolicy(**request.policy.model_dump())
        if request.policy
        else OrchestrationPolicy()
    )

    try:
        orchestrator = LLMOrchestrator(
            llm_client=client_factory.get_client(request.provider),
            registry=tool_registry,
            adapter=adapter,
            model=request.core_model,
            policy=policy,
            config=OrchestratorConfig(
                temperature=request.temperature or 0.1,
                max_tokens=request.max_tokens,
                system_prompt=request.system_prompt,
                custom_instructions=request.custom_instructions,
                model=request.core_model,
            ),
        )

        output = await orchestrator.run(request.input)
    except LLMAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return OrchestrateResponse(
        output=output,
        tool_calls=[
            {
                "tool": result.get("tool", "unknown"),
                "success": bool(result.get("success")),
                "result": result.get("result"),
                "error": result.get("error"),
            }
            for result in orchestrator.last_tool_results
        ],
        usage=None,
    )
