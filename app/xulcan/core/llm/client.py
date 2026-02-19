"""Provider client wrappers for Xulcan orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from xulcan.config import Settings


@dataclass
class LLMResponse:
    content: str
    tool_calls: List[Dict[str, Any]]
    raw: Any = None


class BaseLLMClient:
    async def create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        tool_choice: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        model: str,
    ) -> LLMResponse:
        raise NotImplementedError


class LLMAuthenticationError(Exception):
    """Raised when an LLM provider rejects credentials."""

    def __init__(self, *, provider: str, message: Optional[str] = None) -> None:
        self.provider = provider
        default_message = (
            f"Authentication failed for provider '{provider}'. "
            "Check that the configured API key/token is valid and not expired."
        )
        super().__init__(message or default_message)


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: Optional[str],
        base_url: Optional[str] = None,
        provider: str = "openai",
    ) -> None:
        from openai import AsyncOpenAI, OpenAIError

        self.provider = provider
        try:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        except OpenAIError as exc:
            raise LLMAuthenticationError(provider=self.provider) from exc

    async def create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        tool_choice: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        model: str,
    ) -> LLMResponse:
        from openai import AuthenticationError as OpenAIAuthenticationError

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools or None,
                tool_choice=tool_choice or ("auto" if tools else None),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except OpenAIAuthenticationError as exc:
            raise LLMAuthenticationError(provider=self.provider) from exc

        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for call in message.tool_calls:
                if hasattr(call, "model_dump"):
                    tool_calls.append(call.model_dump())
                else:
                    tool_calls.append(call)
        return LLMResponse(
            content=message.content or "", tool_calls=tool_calls, raw=response
        )


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str]) -> None:
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=api_key)

    def _to_anthropic_messages(
        self, messages: List[Dict[str, Any]]
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        system_parts: List[str] = []
        converted: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(str(content))
                continue

            if role == "tool":
                tool_use_id = msg.get("tool_call_id") or msg.get("id") or ""
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": str(content),
                            }
                        ],
                    }
                )
                continue

            if isinstance(content, list):
                converted.append({"role": role, "content": content})
            else:
                converted.append(
                    {"role": role, "content": [{"type": "text", "text": str(content)}]}
                )

        system = "\n".join(system_parts) if system_parts else None
        return system, converted

    async def create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        tool_choice: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        model: str,
    ) -> LLMResponse:
        system, converted = self._to_anthropic_messages(messages)

        choice: Any = tool_choice
        if tool_choice is None and tools:
            choice = {"type": "auto"}
        elif isinstance(tool_choice, str):
            choice = {"type": tool_choice}

        response = await self.client.messages.create(
            model=model,
            system=system,
            messages=converted,
            tools=tools or None,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
            tool_choice=choice,
        )

        content_text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for block in response.content:
            block_type = getattr(block, "type", None) or block.get("type")
            if block_type == "text":
                text = getattr(block, "text", None) or block.get("text")
                if text:
                    content_text_parts.append(text)
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "type": "tool_use",
                        "id": getattr(block, "id", None) or block.get("id"),
                        "name": getattr(block, "name", None) or block.get("name"),
                        "input": getattr(block, "input", None)
                        or block.get("input", {}),
                    }
                )

        return LLMResponse(
            content="".join(content_text_parts),
            tool_calls=tool_calls,
            raw=response,
        )


class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str]) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.genai = genai

    def _messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                parts.append(str(content))
            elif role == "tool":
                parts.append(f"tool_result: {content}")
            else:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    async def create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        tool_choice: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        model: str,
    ) -> LLMResponse:
        prompt = self._messages_to_prompt(messages)
        gen_model = self.genai.GenerativeModel(model)

        kwargs: Dict[str, Any] = {
            "contents": prompt,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        }

        if tools:
            kwargs["tools"] = [{"function_declarations": tools}]
            if tool_choice:
                kwargs["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}

        response = await asyncio.to_thread(gen_model.generate_content, **kwargs)

        content_text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            parts = candidates[0].content.parts
            for part in parts:
                if hasattr(part, "text") and part.text:
                    content_text_parts.append(part.text)
                if hasattr(part, "function_call") and part.function_call:
                    tool_calls.append({"function_call": part.function_call})

        return LLMResponse(
            content="".join(content_text_parts),
            tool_calls=tool_calls,
            raw=response,
        )


class LLMClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._clients: Dict[str, BaseLLMClient] = {}

    def get_client(self, provider: str) -> BaseLLMClient:
        if provider in self._clients:
            return self._clients[provider]

        if provider == "openai":
            client = OpenAIClient(
                api_key=(
                    self.settings.OPENAI_API_KEY.get_secret_value()
                    if self.settings.OPENAI_API_KEY
                    else None
                ),
                provider="openai",
            )
        elif provider == "zai":
            client = OpenAIClient(
                api_key=(
                    self.settings.ZAI_API_KEY.get_secret_value()
                    if self.settings.ZAI_API_KEY
                    else None
                ),
                base_url=self.settings.ZAI_BASE_URL,
                provider="zai",
            )
        elif provider == "openrouter":
            client = OpenAIClient(
                api_key=(
                    self.settings.OPENROUTER_API_KEY.get_secret_value()
                    if self.settings.OPENROUTER_API_KEY
                    else None
                ),
                base_url=self.settings.OPENROUTER_BASE_URL,
                provider="openrouter",
            )
        elif provider == "anthropic":
            client = AnthropicClient(
                api_key=(
                    self.settings.ANTHROPIC_API_KEY.get_secret_value()
                    if self.settings.ANTHROPIC_API_KEY
                    else None
                )
            )
        elif provider == "gemini":
            client = GeminiClient(
                api_key=(
                    self.settings.GEMINI_API_KEY.get_secret_value()
                    if self.settings.GEMINI_API_KEY
                    else None
                )
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        self._clients[provider] = client
        return client
