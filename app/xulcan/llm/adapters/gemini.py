"""Gemini LLM adapter with typed ConfigSchema."""

from __future__ import annotations

import time
import uuid
import json
import base64
from typing import Any
from pydantic import Field

from google import genai
from google.genai import types
from google.genai.errors import APIError
from xulcan.llm.exceptions import TransientLLMError, FatalLLMError

from xulcan.core import ExternalID, SemanticText, UsageStats
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

class GeminiConfig(BaseLLMConfig):
    """Configuration contract for GeminiAdapter.
    
    api_key lives here (infrastructure credential injected at build time).
    model_name, temperature, max_tokens inherited from BaseLLMConfig (cognitive params).
    """
    api_key: ExternalID = Field(
        description="Google AI API key. Injected by VaultStore/app.py, never from Blueprint."
    )
  


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════════════════

class GeminiAdapter(BaseLLMAdapter):
    """Adapter for Google's Gemini models using the new genai SDK."""

    ConfigSchema = GeminiConfig

    def __init__(self, config: GeminiConfig):
        super().__init__(config)
        # Client instantiated ONCE at construction time, not per inference call
        self.client = genai.Client(api_key=config.api_key)

    async def _generate_impl(
        self,
        messages: list[UnifiedMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any
    ) -> UnifiedResponse:

        start_time = time.time()
        gemini_messages: list[types.Content] =[]
        system_instruction = None

        # ════════════════════════════════════════════════════════════════════
        # 1. INPUT TRANSLATION (Xulcan → Gemini)
        # ════════════════════════════════════════════════════════════════════
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_instruction = msg.content

            elif isinstance(msg, UserMessage):
                parts =[]
                if isinstance(msg.content, str):
                    parts.append(types.Part.from_text(text=msg.content))
                else:
                    # Multimodal Support (Images, Audio, Text)
                    for part in msg.content:
                        if isinstance(part, TextPart):
                            parts.append(types.Part.from_text(text=part.text))
                        elif isinstance(part, (ImagePart, AudioPart)):
                            if part.data:
                                decoded_bytes = base64.b64decode(part.data)
                                parts.append(types.Part.from_bytes(
                                    data=decoded_bytes, 
                                    mime_type=part.media_type
                                ))
                            elif part.url:
                                # The genai SDK prefers bytes or Google Cloud Storage URIs.
                                # For external HTTP URLs, we pass it as text context.
                                parts.append(types.Part.from_text(
                                    text=f"[Media attachment located at: {part.url}]"
                                ))
                
                gemini_messages.append(types.Content(role="user", parts=parts))

            elif isinstance(msg, AssistantMessage):
                if msg.tool_calls:
                    parts =[
                        types.Part.from_function_call(name=tc.name, args=tc.arguments)
                        for tc in msg.tool_calls
                    ]
                    gemini_messages.append(types.Content(role="model", parts=parts))
                elif msg.content:
                    gemini_messages.append(types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=msg.content)]
                    ))

            elif isinstance(msg, ToolMessage):
                # Safely extract string content even if it's a list of parts
                content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
                try:
                    parsed = json.loads(content_str)
                    resp_dict = parsed if isinstance(parsed, dict) else {"result": parsed}
                except (json.JSONDecodeError, TypeError):
                    resp_dict = {"result": content_str}

                gemini_messages.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=msg.name or "unknown_tool",
                        response=resp_dict
                    )]
                ))

        # ════════════════════════════════════════════════════════════════════
        # 2. TOOL DEFINITIONS
        # ════════════════════════════════════════════════════════════════════
        gemini_tools = None
        if tools:
            declarations =[
                types.FunctionDeclaration(
                    name=t.function.name,
                    description=t.function.description or "",
                    parameters=t.function.parameters
                )
                for t in tools
            ]
            gemini_tools =[types.Tool(function_declarations=declarations)]

        # ════════════════════════════════════════════════════════════════════
        # 3. API CALL — uses self.config for all cognitive parameters
        # ════════════════════════════════════════════════════════════════════
        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            tools=gemini_tools,
            system_instruction=system_instruction
        )
        if self.config.max_tokens:
            config.max_output_tokens = self.config.max_tokens

        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model_name,
                contents=gemini_messages,
                config=config
            )
        except APIError as e:
            if e.code in [404, 429, 500, 503]:
                raise TransientLLMError(f"Gemini transient error ({e.code}): {e.message}")
            raise FatalLLMError(f"Gemini fatal error ({e.code}): {e.message}")

        # ════════════════════════════════════════════════════════════════════
        # 4. OUTPUT TRANSLATION (Gemini → Xulcan)
        # ════════════════════════════════════════════════════════════════════
        tool_calls_out =[]
        text_content = ""
        finish_reason = FinishReason.STOP

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call:
                        # Gemini natively doesn't return tool call IDs, we generate them for traceability
                        tool_calls_out.append(ToolCall(
                            id=f"call_{uuid.uuid4().hex[:8]}",
                            name=part.function_call.name,
                            arguments=dict(part.function_call.args) # type: ignore
                        ))
                    elif part.text:
                        text_content += part.text
            else:
                motivo = getattr(candidate, "finish_reason", "UNKNOWN")
                text_content = (
                    f"[XULCAN WARNING] Google blocked the response. "
                    f"finish_reason: {motivo}"
                )
                finish_reason = FinishReason.CONTENT_FILTER

        if tool_calls_out:
            finish_reason = FinishReason.TOOL_CALLS

        in_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
        out_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
        latency = float((time.time() - start_time) * 1000)

        return UnifiedResponse(
            content=text_content if text_content else None,
            tool_calls=tool_calls_out if tool_calls_out else None,
            finish_reason=finish_reason,
            usage=UsageStats(
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=in_tokens + out_tokens,
                latency_ms=latency
            )
        )