"""Output extraction pipelines for handling non-compliant local models."""

from __future__ import annotations

import re
import json
import uuid

from xulcan.protocol.tools import ToolCall


class OutputExtractor:
    """Extraction and sanitization pipeline for local, non-API-compliant models."""

    @staticmethod
    def strip_think_tags(raw_content: str) -> tuple[str, str | None]:
        """Anti-Think shield for reasoning models (e.g., DeepSeek R1).
        
        Extracts the internal reasoning process (Chain-of-Thought) and removes
        it from the main response content, preventing the UI from rendering it
        or tools from parsing it.
        """
        if not raw_content or "<think>" not in raw_content:
            return raw_content, None
            
        think_match = re.search(r'<think>(.*?)</think>', raw_content, flags=re.DOTALL)
        reasoning = think_match.group(1).strip() if think_match else None
        
        clean_content = re.sub(r'<think>.*?</think>\n?', '', raw_content, flags=re.DOTALL).strip()
        
        return clean_content, reasoning

    @staticmethod
    def extract_rebel_json(content: str) -> tuple[list[ToolCall], str]:
        """Hunts for rogue JSON blocks in plain text responses.
        
        Used by the PromptInjectionStrategy when models fail to use the official
        tool-calling API and instead dump the tool request as raw text.
        """
        tool_calls: list[ToolCall] =[]
        
        # 1. Search within markdown code blocks first
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, flags=re.DOTALL)
        target_str = json_match.group(1) if json_match else content

        # 2. Mathematical bracket search (fallback for missing markdown)
        start_idx = target_str.find('{')
        end_idx = target_str.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            extracted_json = target_str[start_idx:end_idx + 1]
            
            try:
                tool_data = json.loads(extracted_json)
                call_info = None
                
                # Support multiple injected formats (wrapped vs direct)
                if "tool_call" in tool_data:
                    call_info = tool_data["tool_call"]
                elif "name" in tool_data and "arguments" in tool_data:
                    call_info = tool_data

                if call_info:
                    args = call_info.get("arguments", {})
                    
                    # Fix for models that double-escape the JSON as a string
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            # If it's a completely broken string, wrap it safely
                            args = {"raw_arguments": args}

                    tool_calls.append(ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=call_info.get("name", "unknown_tool"),
                        arguments=args
                    ))
                    
                    # Clean the extracted JSON block from the visible text
                    content = content.replace(extracted_json, "").strip()
                    # Only strip empty markdown blocks left behind
                    content = re.sub(r'```(?:json)?\s*```', '', content).strip()
                    
            except json.JSONDecodeError:
                # The brackets didn't contain valid JSON (e.g., just prose)
                pass

        return tool_calls, content