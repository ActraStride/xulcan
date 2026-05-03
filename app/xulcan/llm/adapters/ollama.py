"""Ollama LLM adapter with intelligent tool fallback and typed ConfigSchema."""

from __future__ import annotations

import time
import uuid
import json
import logging
from typing import Any
from pydantic import Field

from ollama import AsyncClient, ResponseError

from xulcan.core import ExternalID, UsageStats
from xulcan.llm.base import BaseLLMAdapter, BaseLLMConfig
from xulcan.protocol.message import (
    UnifiedMessage, SystemMessage, UserMessage, 
    AssistantMessage, ToolMessage
)
from xulcan.protocol.parts import TextPart
from xulcan.protocol.io import UnifiedResponse, FinishReason
from xulcan.protocol.tools import ToolCall, ToolDefinition

# Import common strategies for handling local models
from xulcan.llm.adapters.common.strategies import NativeToolStrategy, PromptInjectionStrategy
from xulcan.llm.adapters.common.extractors import OutputExtractor


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class OllamaConfig(BaseLLMConfig):
    """Configuration contract for OllamaAdapter.
    
    Inherits model_name, temperature, and max_tokens from BaseLLMConfig.
    Adds Ollama-specific infrastructure parameters.
    """
    host: str = Field(
        default="http://localhost:11434",
        description="URL of the Ollama server."
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class OllamaAdapter(BaseLLMAdapter):
    """Clean, Strategy-based Adapter for local models on Ollama."""
    
    ConfigSchema = OllamaConfig
    
    def __init__(self, config: OllamaConfig):
        super().__init__(config)
        # Client instantiated ONCE at construction time
        self.client = AsyncClient(host=config.host)
        # Tracks models that fail native tool calling to automatically apply fallbacks
        self._fallback_cache: set[str] = set()

    def _translate_messages(self, messages: list[UnifiedMessage]) -> list[dict[str, Any]]:
        """Translates Xulcan UnifiedMessage format into Ollama's dict format."""
        ollama_messages =[]
        for msg in messages:
            if isinstance(msg, SystemMessage):
                ollama_messages.append({"role": "system", "content": str(msg.content)})
                
            elif isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    content_str = msg.content
                else:
                    # Graceful degradation for multimodal content: extract only text parts
                    content_str = " ".join([
                        part.text for part in msg.content if isinstance(part, TextPart)
                    ])
                ollama_messages.append({"role": "user", "content": content_str})
                
            elif isinstance(msg, AssistantMessage):
                msg_dict: dict[str, Any] = {
                    "role": "assistant", 
                    "content": msg.content or ""
                }
                if msg.tool_calls:
                    msg_dict["tool_calls"] =[
                        {"function": {"name": tc.name, "arguments": tc.arguments}} 
                        for tc in msg.tool_calls
                    ]
                ollama_messages.append(msg_dict)
                
            elif isinstance(msg, ToolMessage):
                # Ollama expects tool outputs as strings
                content_str = (
                    json.dumps(msg.content) if isinstance(msg.content, (dict, list)) 
                    else str(msg.content)
                )
                ollama_messages.append({
                    "role": "tool", 
                    "content": content_str, 
                    "name": msg.name
                })
                
        return ollama_messages

    async def _generate_impl(
        self,
        messages: list[UnifiedMessage], 
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any
    ) -> UnifiedResponse:
        
        start_time = time.time()
        ollama_messages = self._translate_messages(messages)
        
        options: dict[str, Any] = {"temperature": self.config.temperature}
        if self.config.max_tokens: 
            options["num_predict"] = self.config.max_tokens

        model = self.config.model_name

        # 1. SELECT STRATEGY (Native vs Prompt Injection)
        requires_fallback = model in self._fallback_cache
        strategy = PromptInjectionStrategy() if requires_fallback else NativeToolStrategy()
        
        final_msgs, api_tools = strategy.apply(ollama_messages, tools)

        # 2. OLLAMA API INVOCATION
        try:
            response = await self.client.chat(
                model=model, 
                messages=final_msgs, 
                tools=api_tools, 
                options=options
            )
        except ResponseError as e:
            # Auto-detect models that lack native tool support (e.g., small 7B models)
            if not requires_fallback and ("does not support tools" in str(e).lower() or e.status_code == 400):
                logger.warning(
                    f"Ollama model '{model}' does not support native tools. "
                    "Caching state and activating Prompt Injection Fallback Strategy..."
                )
                self._fallback_cache.add(model)
                strategy = PromptInjectionStrategy()
                final_msgs, api_tools = strategy.apply(ollama_messages, tools)
                
                # Retry with the fallback strategy
                response = await self.client.chat(
                    model=model, 
                    messages=final_msgs, 
                    options=options
                )
            else:
                raise e

        # 3. EXTRACTION AND SANITIZATION
        raw_msg = response.get("message", {})
        content = raw_msg.get("content", "")
        
        # DeepSeek R1 / Llama 3 style think tags removal
        content, reasoning = OutputExtractor.strip_think_tags(content)
        
        tool_calls_out =[]
        if "tool_calls" in raw_msg and raw_msg["tool_calls"]:
            # Native tool calls returned by Ollama
            for tc in raw_msg["tool_calls"]:
                func = tc.get("function", {})
                tool_calls_out.append(ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=func.get("name", ""), 
                    arguments=func.get("arguments", {})
                ))
        elif tools:
            # Fallback strategy: Extract JSON from standard text output
            rebel_tools, content = OutputExtractor.extract_rebel_json(content)
            tool_calls_out.extend(rebel_tools)

        in_tokens = response.get("prompt_eval_count", 0) or 0
        out_tokens = response.get("eval_count", 0) or 0

        # 4. RETURN XULCAN STANDARD RESPONSE
        return UnifiedResponse(
            content=content if content else None,
            reasoning_content=reasoning if reasoning else None,
            tool_calls=tool_calls_out if tool_calls_out else None,
            finish_reason=FinishReason.TOOL_CALLS if tool_calls_out else FinishReason.STOP,
            usage=UsageStats(
                input_tokens=in_tokens, 
                output_tokens=out_tokens, 
                total_tokens=in_tokens + out_tokens,
                latency_ms=float((time.time() - start_time) * 1000)
            )
        )