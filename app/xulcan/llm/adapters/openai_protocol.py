"""OpenAI-compatible LLM adapter with typed ConfigSchema."""

from __future__ import annotations

import time
import json
from typing import Any
from pydantic import Field
from openai import AsyncOpenAI
from openai import APIError, APIConnectionError, APITimeoutError
from xulcan.llm.exceptions import TransientLLMError, FatalLLMError

from xulcan.core import ExternalID, SafeURL, UsageStats
from xulcan.llm.base import BaseLLMAdapter, BaseLLMConfig
from xulcan.protocol.message import (
    UnifiedMessage, SystemMessage, UserMessage,
    AssistantMessage, ToolMessage
)
from xulcan.protocol.parts import TextPart, ImagePart, AudioPart
from xulcan.protocol.io import UnifiedResponse, FinishReason
from xulcan.protocol.tools import ToolCall, ToolDefinition


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

class OpenAICompatibleConfig(BaseLLMConfig):
    """Configuration for any OpenAI-protocol compatible provider.
    
    Covers: OpenAI, Groq, DeepSeek, xAI, OpenRouter, vLLM, etc.
    Subclasses can override base_url and model_name defaults.
    """
    api_key: ExternalID = Field(
        description="API key. Injected by VaultStore/app.py, never from Blueprint."
    )
    
    base_url: SafeURL | None = Field(
        default=None,
        description="Custom base URL (None = OpenAI default). Set for Groq, DeepSeek, etc."
    )
    
   

# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class OpenAICompatibleAdapter(BaseLLMAdapter):
    """Universal adapter for any LLM provider implementing the OpenAI API standard.
    
    Covers: OpenAI, Groq, DeepSeek, xAI, OpenRouter, vLLM, and any
    OpenAI-compatible endpoint.
    
    Subclass and set ConfigSchema + default model_name to specialize.
    """

    ConfigSchema = OpenAICompatibleConfig

    def __init__(self, config: OpenAICompatibleConfig):
        super().__init__(config)
        # Client instantiated ONCE at construction time
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )

    async def _generate_impl(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any
    ) -> UnifiedResponse:

        start_time = time.time()

        # ════════════════════════════════════════════════════════════════════
        # 1. INPUT TRANSLATION (Xulcan → OpenAI Standard)
        # ════════════════════════════════════════════════════════════════════
        oai_messages: list[dict[str, Any]] =[]

        for msg in messages:
            if isinstance(msg, SystemMessage):
                oai_messages.append({"role": "system", "content": str(msg.content)})

            elif isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    oai_messages.append({"role": "user", "content": msg.content})
                else:
                    # Multimodal Translation
                    parts =[]
                    for part in msg.content:
                        if isinstance(part, TextPart):
                            parts.append({"type": "text", "text": part.text})
                        elif isinstance(part, ImagePart):
                            if part.url:
                                parts.append({"type": "image_url", "image_url": {"url": part.url}})
                            elif part.data:
                                # OpenAI requires Base64 images to be formatted as Data URIs
                                data_uri = f"data:{part.media_type};base64,{part.data}"
                                parts.append({"type": "image_url", "image_url": {"url": data_uri}})
                        elif isinstance(part, AudioPart):
                            # Audio input support depends heavily on the specific provider.
                            # We downgrade to text reference to avoid crashing standard endpoints.
                            parts.append({"type": "text", "text": f"[Audio Attachment: {part.media_type}]"})
                            
                    oai_messages.append({"role": "user", "content": parts})

            elif isinstance(msg, AssistantMessage):
                oai_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    oai_msg["tool_calls"] =[
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
                oai_messages.append(oai_msg)

            elif isinstance(msg, ToolMessage):
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(msg, 'tool_call_id', 'unknown'),
                    "content": str(msg.content)
                })

        # ════════════════════════════════════════════════════════════════════
        # 2. TOOL DEFINITIONS
        # ════════════════════════════════════════════════════════════════════
        oai_tools = None
        if tools:
            oai_tools =[
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
        # 3. API CALL — reads all cognitive params from self.config
        # ════════════════════════════════════════════════════════════════════
        api_kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": oai_messages,
            "temperature": self.config.temperature,
        }
        if oai_tools:
            api_kwargs["tools"] = oai_tools
        if self.config.max_tokens:
            api_kwargs["max_tokens"] = self.config.max_tokens

        # Merge any extra kwargs passed directly
        api_kwargs.update(kwargs)

        try:
            response = await self.client.chat.completions.create(**api_kwargs)
        except (APITimeoutError, APIConnectionError) as e:
            raise TransientLLMError(f"Network issue with {self.config.model_name}: {e}")
        except APIError as e:
            # 429 = Rate Limit, 5xx = Server Error
            if e.status_code in [401, 429, 500, 502, 503, 504]:
                raise TransientLLMError(f"Transient provider error ({e.status_code}): {e.message}")
            raise FatalLLMError(f"Fatal provider error ({e.status_code}): {e.message}")
        except Exception as e:
            raise FatalLLMError(f"Unexpected error in OpenAI protocol: {e}")


        # ════════════════════════════════════════════════════════════════════
        # 4. OUTPUT TRANSLATION (OpenAI Standard → Xulcan)
        # ════════════════════════════════════════════════════════════════════
        choice = response.choices[0]
        msg_out = choice.message

        # Usamos un nombre diferente para evitar el bug de renderizado
        extracted_tools = list()
        
        if msg_out.tool_calls:
            for tc in msg_out.tool_calls:
                try:
                    args_dict = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    # Si el LLM alucina JSON inválido, lo pasamos como raw_arguments
                    # El ToolExecutor o el Sentinel se encargarán de rechazarlo.
                    args_dict = {"raw_arguments": tc.function.arguments}

                extracted_tools.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args_dict
                ))

        # Determinar la razón de finalización según el estándar
        finish_reason = FinishReason.STOP
        if choice.finish_reason == "tool_calls":
            finish_reason = FinishReason.TOOL_CALLS
        elif choice.finish_reason == "length":
            finish_reason = FinishReason.LENGTH
        elif choice.finish_reason == "content_filter":
            finish_reason = FinishReason.CONTENT_FILTER

        # Extraer métricas de uso y latencia
        usage = response.usage
        in_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
        out_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
        latency = float((time.time() - start_time) * 1000)

        return UnifiedResponse(
            content=msg_out.content,
            tool_calls=extracted_tools if extracted_tools else None,
            finish_reason=finish_reason,
            usage=UsageStats(
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=in_tokens + out_tokens,
                latency_ms=latency
            )
        )