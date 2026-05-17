# --- START OF FILE mistral.py ---

"""Mistral native LLM adapter with typed ConfigSchema."""

from __future__ import annotations

import time
import json
import uuid
from typing import Any
from pydantic import Field

from mistralai import Mistral
from mistralai.models import AssistantMessage as MistralAssistantMessage
from mistralai.models import SDKError # Asegúrate de importar esto

from xulcan.llm.exceptions import TransientLLMError, FatalLLMError


from xulcan.core import ExternalID, UsageStats
from xulcan.llm.base import BaseLLMAdapter, BaseLLMConfig
from xulcan.protocol.message import (
    UnifiedMessage, SystemMessage, UserMessage,
    AssistantMessage, ToolMessage
)
from xulcan.protocol.parts import TextPart, ImagePart
from xulcan.protocol.io import UnifiedResponse, FinishReason
from xulcan.protocol.tools import ToolCall, ToolDefinition


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class MistralConfig(BaseLLMConfig):
    """Configuration contract for MistralAdapter."""
    api_key: ExternalID = Field(
        description="Mistral API key. Injected by VaultStore/app.py."
    )
 
    safe_prompt: bool = Field(
        default=False,
        description="Mistral-specific: injects a safety prompt before the conversation."
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class MistralAdapter(BaseLLMAdapter):
    """Adapter for Mistral's official SDK.
    
    Provides native access to Mistral's highly optimized tool-calling
    models and the Pixtral multimodal family, with great free tiers.
    """

    ConfigSchema = MistralConfig

    def __init__(self, config: MistralConfig):
        super().__init__(config)
        # Client instantiated ONCE
        self.client = Mistral(api_key=config.api_key)

    async def _generate_impl(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any
    ) -> UnifiedResponse:

        start_time = time.time()
        mistral_messages: list[dict[str, Any]] =[]

        # ════════════════════════════════════════════════════════════════════
        # 1. INPUT TRANSLATION (Xulcan → Mistral)
        # ════════════════════════════════════════════════════════════════════
        for msg in messages:
            if isinstance(msg, SystemMessage):
                mistral_messages.append({"role": "system", "content": str(msg.content)})

            elif isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    mistral_messages.append({"role": "user", "content": msg.content})
                else:
                    # Multimodal Translation (for Pixtral models)
                    parts =[]
                    for part in msg.content:
                        if isinstance(part, TextPart):
                            parts.append({"type": "text", "text": part.text})
                        elif isinstance(part, ImagePart):
                            if part.url:
                                parts.append({"type": "image_url", "image_url": {"url": part.url}})
                            elif part.data:
                                data_uri = f"data:{part.media_type};base64,{part.data}"
                                parts.append({"type": "image_url", "image_url": {"url": data_uri}})
                    mistral_messages.append({"role": "user", "content": parts})

            elif isinstance(msg, AssistantMessage):
                # Using the SDK's internal class for Assistant messages with tool calls
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
                mistral_messages.append(msg_dict)

            elif isinstance(msg, ToolMessage):
                mistral_messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(msg, 'tool_call_id', 'unknown'),
                    "name": msg.name,
                    "content": json.dumps(msg.content) if isinstance(msg.content, (dict, list)) else str(msg.content)
                })

        # ════════════════════════════════════════════════════════════════════
        # 2. TOOL DEFINITIONS
        # ════════════════════════════════════════════════════════════════════
        mistral_tools = None
        if tools:
            mistral_tools =[
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
            "messages": mistral_messages,
            "temperature": self.config.temperature,
            "safe_prompt": self.config.safe_prompt
        }
        if mistral_tools:
            api_kwargs["tools"] = mistral_tools
        if self.config.max_tokens:
            api_kwargs["max_tokens"] = self.config.max_tokens

        try:
            response = await self.client.chat.complete_async(**api_kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            # 429: Rate limit, 500-504: Server errors
            if any(code in err_msg for code in ["429", "500", "503", "timeout"]):
                raise TransientLLMError(f"Mistral temporalmente offline: {e}")
            raise FatalLLMError(f"Error crítico en Mistral: {e}")
        
        # ════════════════════════════════════════════════════════════════════
        # 4. OUTPUT TRANSLATION (Mistral → Xulcan)
        # ════════════════════════════════════════════════════════════════════
        choice = response.choices[0]
        msg_out = choice.message
        
        extracted_tools = list()
        finish_reason = FinishReason.STOP

        if msg_out.tool_calls:
            for tc in msg_out.tool_calls:
                try:
                    # Mistral SDK sometimes returns arguments as dict or string depending on version
                    args = tc.function.arguments
                    args_dict = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    args_dict = {"raw_arguments": str(tc.function.arguments)}

                extracted_tools.append(ToolCall(
                    id=tc.id or f"call_{uuid.uuid4().hex[:8]}",
                    name=tc.function.name,
                    arguments=args_dict
                ))
            finish_reason = FinishReason.TOOL_CALLS
            
        elif choice.finish_reason == "length":
            finish_reason = FinishReason.LENGTH
        elif choice.finish_reason == "model_length":
            finish_reason = FinishReason.LENGTH

        in_tokens = getattr(response.usage, 'prompt_tokens', 0) if response.usage else 0
        out_tokens = getattr(response.usage, 'completion_tokens', 0) if response.usage else 0

        # Note: Mistral content can occasionally be a list of parts, we flatten to string
        final_text = ""
        if isinstance(msg_out.content, list):
            final_text = "".join([getattr(c, "text", str(c)) for c in msg_out.content])
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

# --- END OF FILE mistral.py ---