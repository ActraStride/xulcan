"""LLM orchestrator for intelligent tool execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from xulcan.core.engine.execution import ExecutionEngine
from xulcan.core.engine.policies import OrchestrationPolicy
from xulcan.core.llm.adapters.base import BaseAdapter
from xulcan.core.llm.client import BaseLLMClient, LLMResponse
from xulcan.core.memory.conversation import ConversationManager
from xulcan.tools.registry import ToolRegistry
from xulcan.tools.runner import ToolRunner


class OrchestratorConfig(BaseModel):
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    custom_instructions: Optional[str] = None
    enable_memory: bool = True
    parallel_tool_calls: bool = True
    max_retries: int = 3


class LLMOrchestrator:
    """Intelligent orchestrator that selects and executes tools."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        registry: ToolRegistry,
        adapter: BaseAdapter,
        model: str,
        policy: Optional[OrchestrationPolicy] = None,
        config: Optional[OrchestratorConfig] = None,
    ) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.adapter = adapter
        self.model = model
        self.policy = policy or OrchestrationPolicy()
        self.config = config or OrchestratorConfig()

        self.runner = ToolRunner(registry)
        self.execution_engine = ExecutionEngine(self.runner, adapter)
        self.conversation = (
            ConversationManager() if self.config.enable_memory else None
        )
        self.last_tool_results: List[Dict[str, Any]] = []

        self.system_prompt = self._create_system_prompt()

    def _create_system_prompt(self) -> str:
        if self.config.system_prompt:
            return self.config.system_prompt
        return self.adapter.create_system_prompt(
            self.registry, custom_instructions=self.config.custom_instructions
        )

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        if self.conversation:
            messages.extend(self.conversation.get_messages())

        messages.append({"role": "user", "content": user_input})
        return messages

    def _get_tool_call_id(self, tool_call: Dict[str, Any]) -> Optional[str]:
        return tool_call.get("id") or tool_call.get("tool_call_id")

    async def run(self, user_input: str) -> str:
        if self.conversation:
            self.conversation.add_message("user", user_input)

        messages = self._build_messages(user_input)
        tools = self.adapter.export_tools(self.registry) if len(self.registry) else []
        self.last_tool_results = []

        for _ in range(self.policy.max_iterations):
            response = await self._call_llm(messages, tools)

            assistant_message: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content,
            }
            if response.tool_calls:
                assistant_message["tool_calls"] = response.tool_calls
            messages.append(assistant_message)

            if not response.tool_calls:
                if self.conversation:
                    self.conversation.add_message("assistant", response.content)
                return response.content

            tool_results = await self._execute_tools(response.tool_calls)
            self.last_tool_results.extend(tool_results)

            for tool_call, tool_result in zip(response.tool_calls, tool_results):
                result_payload = (
                    tool_result.get("result")
                    if tool_result.get("success")
                    else {"error": tool_result.get("error")}
                )
                tool_message = self.adapter.format_tool_result(
                    result_payload, tool_call_id=self._get_tool_call_id(tool_call)
                )
                messages.append(tool_message)

            if not any(r.get("success") for r in tool_results):
                break

        return self._summarize_results(messages)

    async def _call_llm(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> LLMResponse:
        return await self.llm_client.create_chat_completion(
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            model=self.config.model or self.model,
        )

    async def _execute_tools(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if self.config.parallel_tool_calls:
            return await self.execution_engine.execute_tools_parallel(
                tool_calls, max_retries=self.config.max_retries
            )
        return await self.execution_engine.execute_tools_sequential(
            tool_calls, max_retries=self.config.max_retries
        )

    def _summarize_results(self, messages: List[Dict[str, Any]]) -> str:
        return "I couldn't complete the request with available tools."

    def reset_conversation(self) -> None:
        if self.conversation:
            self.conversation.clear()
