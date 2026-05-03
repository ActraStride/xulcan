"""Strategies for injecting tool definitions into local LLMs.

Provides elegant degradation for models running on Ollama that do not 
natively support the Tool Calling API (e.g., 7B parameter models, DeepSeek R1).
"""

from __future__ import annotations

import json
from typing import Any

from xulcan.protocol.tools import ToolDefinition


class ToolingStrategy:
    """Base interface for Tool Calling strategies."""
    
    def apply(
        self, 
        messages: list[dict[str, Any]], 
        tools: list[ToolDefinition] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Apply the tool configuration to the conversation history.
        
        Args:
            messages: The Ollama-formatted conversation history.
            tools: The list of available Xulcan ToolDefinitions.
            
        Returns:
            A tuple of (Modified Messages, Native Ollama Tools).
        """
        raise NotImplementedError


class NativeToolStrategy(ToolingStrategy):
    """For Tier 1 Models (e.g., Qwen 32B, Llama 3.3). Uses the official API."""
    
    def apply(
        self, 
        messages: list[dict[str, Any]], 
        tools: list[ToolDefinition] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        
        ollama_tools: list[dict[str, Any]] =[]
        if tools:
            for t in tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "description": t.function.description or "",
                        "parameters": t.function.parameters
                    }
                })
        return messages, ollama_tools if ollama_tools else None


class PromptInjectionStrategy(ToolingStrategy):
    """For Tier 2 Models (e.g., 7B-8B, R1). Injects instructions directly into System Prompt.
    
    This strategy bypasses Ollama's native tool validation and relies on the 
    model's instruction-following capabilities to output a raw JSON block.
    """
    
    def apply(
        self, 
        messages: list[dict[str, Any]], 
        tools: list[ToolDefinition] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        
        if not tools:
            return messages, None
            
        # Note: We use English for system prompts as small models (7B) 
        # have significantly better instruction-following capabilities in English.
        prompt = (
            "\n\n*** STRICT TOOL USAGE INSTRUCTIONS ***\n"
            "You have access to the following tools:\n"
        )
        
        for t in tools:
            params_str = json.dumps(t.function.parameters, indent=2)
            prompt += (
                f"- Name: {t.function.name}\n"
                f"  Description: {t.function.description}\n"
                f"  Required Arguments Schema:\n{params_str}\n\n"
            )
        
        prompt += (
            "If you need to use a tool, you MUST respond ONLY with a JSON block "
            "matching exactly this format. Do not add any text outside the JSON block:\n"
            "```json\n"
            "{\n"
            "  \"tool_call\": {\n"
            "    \"name\": \"tool_name_here\",\n"
            "    \"arguments\": {\"arg1\": \"value1\"}\n"
            "  }\n"
            "}\n"
            "```"
        )
        
        new_messages = list(messages)
        if new_messages and new_messages[0]["role"] == "system":
            new_messages[0]["content"] += prompt
        else:
            new_messages.insert(0, {"role": "system", "content": prompt})
            
        # Return None for API tools to prevent Ollama from returning 400 errors
        return new_messages, None