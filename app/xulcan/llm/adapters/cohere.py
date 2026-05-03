# --- START OF FILE cohere.py ---

"""Cohere LLM adapter natively optimized for Command R and Command R+."""

from __future__ import annotations

import time
import uuid
import json
from typing import Any
from pydantic import Field

from cohere import AsyncClientV2
from cohere.core.api_error import ApiError
from xulcan.llm.exceptions import TransientLLMError, FatalLLMError


from xulcan.core import ExternalID, UsageStats
from xulcan.llm.base import BaseLLMAdapter, BaseLLMConfig
from xulcan.protocol.message import (
    UnifiedMessage, SystemMessage, UserMessage,
    AssistantMessage, ToolMessage
)
from xulcan.protocol.parts import TextPart
from xulcan.protocol.io import UnifiedResponse, FinishReason
from xulcan.protocol.tools import ToolCall, ToolDefinition


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class CohereConfig(BaseLLMConfig):
    """Configuration contract for CohereAdapter."""
    api_key: ExternalID = Field(
        description="Cohere API key. Injected by VaultStore/app.py."
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class CohereAdapter(BaseLLMAdapter):
    """Adapter for Cohere's Command models using the V2 SDK.
    
    Command R / R+ are highly specialized in RAG and Tool Calling,
    and Cohere offers an unlimited free tier for developers.
    """

    ConfigSchema = CohereConfig

    def __init__(self, config: CohereConfig):
        super().__init__(config)
        self.client = AsyncClientV2(api_key=config.api_key)

    async def _generate_impl(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any
    ) -> UnifiedResponse:

        start_time = time.time()
        cohere_messages: list[dict[str, Any]] =[]

        # ════════════════════════════════════════════════════════════════════
        # 1. INPUT TRANSLATION (Xulcan → Cohere V2)
        # ════════════════════════════════════════════════════════════════════
        for msg in messages:
            if isinstance(msg, SystemMessage):
                cohere_messages.append({"role": "system", "content": str(msg.content)})

            elif isinstance(msg, UserMessage):
                # Cohere is primarily text-based, graceful degradation for multimodality
                if isinstance(msg.content, str):
                    content_str = msg.content
                else:
                    content_str = " ".join([
                        part.text for part in msg.content if isinstance(part, TextPart)
                    ])
                cohere_messages.append({"role": "user", "content": content_str})

            elif isinstance(msg, AssistantMessage):
                msg_dict: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    msg_dict["tool_calls"] =[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                cohere_messages.append(msg_dict)

            elif isinstance(msg, ToolMessage):
                # Cohere V2 expects tool results similarly to OpenAI
                cohere_messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(msg, 'tool_call_id', 'unknown'),
                    "content": json.dumps(msg.content) if isinstance(msg.content, (dict, list)) else str(msg.content)
                })

        # ════════════════════════════════════════════════════════════════════
        # 2. TOOL DEFINITIONS
        # ════════════════════════════════════════════════════════════════════
        cohere_tools = None
        if tools:
            cohere_tools =[
                {
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "description": t.function.description or "",
                        "parameters": t.function.parameters
                    }
                }
                for t in tools
            ]

        # ════════════════════════════════════════════════════════════════════
        # 3. API CALL
        # ════════════════════════════════════════════════════════════════════
        api_kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": cohere_messages,
            "temperature": self.config.temperature,
        }
        if cohere_tools:
            api_kwargs["tools"] = cohere_tools
        if self.config.max_tokens:
            api_kwargs["max_tokens"] = self.config.max_tokens

        # ... dentro de _generate_impl
        try:
            response = await self.client.chat(**api_kwargs)
        except Exception as e:
            # Cohere suele dar 429 muy rápido en el Trial Tier
            if "429" in str(e) or "too many requests" in str(e).lower():
                raise TransientLLMError(f"Cohere Rate Limit alcanzado: {e}")
            raise FatalLLMError(f"Error fatal en Cohere: {e}")

        # ════════════════════════════════════════════════════════════════════
        # 4. OUTPUT TRANSLATION (Cohere → Xulcan)
        # ════════════════════════════════════════════════════════════════════
        msg_out = response.message
        
        extracted_tools = list()
        finish_reason = FinishReason.STOP

        if msg_out.tool_calls:
            for tc in msg_out.tool_calls:
                # Cohere sometimes returns arguments as dict directly depending on the wrapper
                args_dict = tc.function.arguments
                if isinstance(args_dict, str):
                    try:
                        args_dict = json.loads(args_dict)
                    except json.JSONDecodeError:
                        args_dict = {"raw_arguments": args_dict}

                extracted_tools.append(ToolCall(
                    id=tc.id or f"call_{uuid.uuid4().hex[:8]}",
                    name=tc.function.name,
                    arguments=args_dict
                ))
            finish_reason = FinishReason.TOOL_CALLS

        if response.finish_reason == "MAX_TOKENS":
            finish_reason = FinishReason.LENGTH
        
        in_tokens = getattr(response.usage.billed_units, 'input_tokens', 0) if response.usage else 0
        out_tokens = getattr(response.usage.billed_units, 'output_tokens', 0) if response.usage else 0
        
        # Some Cohere models format text inside message.content list
        final_text = ""
        if isinstance(msg_out.content, list):
            final_text = "".join([c.text for c in msg_out.content if c.type == "text"])
        else:
            final_text = str(msg_out.content) if msg_out.content else ""

        return UnifiedResponse(
            content=final_text if final_text else None,
            tool_calls=extracted_tools if extracted_tools else None,
            finish_reason=finish_reason,
            usage=UsageStats(
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=in_tokens + out_tokens,
                latency_ms=float((time.time() - start_time) * 1000)
            )
        )

# --- END OF FILE cohere.py ---