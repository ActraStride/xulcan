#!/usr/bin/env python3
"""Core LLM smoke test (no API route required).

This script is beginner-friendly on purpose:
- It talks directly to the core provider clients.
- It prints green/red/yellow status lines.
- It can be run locally to quickly validate provider wiring.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Optional


# Keep compatibility with issue notes and this repo layout.
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "app"))

from xulcan.config import Settings
from xulcan.core.llm.adapters.gemini import GeminiAdapter
from xulcan.core.llm.adapters.openai import OpenAIAdapter
from xulcan.core.llm.client import LLMClientFactory, LLMResponse
from xulcan.tools.base import BaseTool, tool


RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"


@dataclass
class Counters:
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def _log_info(message: str) -> None:
    print(f"{BLUE}[INFO]{RESET} {message}")


def _log_pass(message: str) -> None:
    print(f"{GREEN}[PASS]{RESET} {message}")


def _log_fail(message: str) -> None:
    print(f"{RED}[FAIL]{RESET} {message}")


def _log_skip(message: str) -> None:
    print(f"{YELLOW}[SKIP]{RESET} {message}")


def _has_secret(secret_obj: Any) -> bool:
    if not secret_obj:
        return False
    try:
        value = secret_obj.get_secret_value()
    except AttributeError:
        value = str(secret_obj)
    return bool(value and str(value).strip())


def _extract_total_tokens(raw_response: Any) -> Optional[int]:
    """Try common token fields across provider SDKs."""
    if raw_response is None:
        return None

    usage = getattr(raw_response, "usage", None)
    if usage is not None:
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int):
            return total
        total = getattr(usage, "total_token_count", None)
        if isinstance(total, int):
            return total

    usage_metadata = getattr(raw_response, "usage_metadata", None)
    if usage_metadata is not None:
        total = getattr(usage_metadata, "total_token_count", None)
        if isinstance(total, int):
            return total

    return None


def _openai_like_candidates(settings: Settings) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    if _has_secret(settings.OPENROUTER_API_KEY):
        candidates.append(
            ("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/free"))
        )
    if _has_secret(settings.OPENAI_API_KEY):
        candidates.append(("openai", os.getenv("OPENAI_MODEL", "gpt-4o-mini")))
    if _has_secret(settings.DEEPSEEK_API_KEY):
        candidates.append(("deepseek", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")))

    return candidates


def _pick_provider_for_tool_test(settings: Settings) -> Optional[tuple[str, str]]:
    # Prefer OpenRouter in local demos because users often configure it first.
    if _has_secret(settings.OPENROUTER_API_KEY):
        return "openrouter", os.getenv("TOOL_TEST_MODEL", "openrouter/free")
    if _has_secret(settings.OPENAI_API_KEY):
        return "openai", os.getenv("TOOL_TEST_MODEL", "gpt-4o-mini")
    if _has_secret(settings.DEEPSEEK_API_KEY):
        return "deepseek", os.getenv("TOOL_TEST_MODEL", "deepseek-chat")
    if _has_secret(settings.GEMINI_API_KEY):
        return "gemini", os.getenv("TOOL_TEST_MODEL", "gemini-1.5-flash")
    return None


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _run_connection_test(
    *,
    label: str,
    provider: str,
    model: str,
    factory: LLMClientFactory,
) -> None:
    _log_info(f"{label}: provider={provider}, model={model}")
    client = factory.get_client(provider)

    response: LLMResponse = await client.create_chat_completion(
        messages=[
            {"role": "user", "content": "Hello from Xulcan! Reply in one sentence."}
        ],
        tools=None,
        tool_choice=None,
        temperature=0,
        max_tokens=200,
        model=model,
    )

    _assert(response is not None, "Response must not be None")
    _assert(isinstance(response.content, str), "response.content must be a string")

    total_tokens = _extract_total_tokens(response.raw)
    _assert(
        isinstance(total_tokens, int) and total_tokens > 0,
        "response usage.total_tokens should be > 0",
    )

    preview = response.content.strip().replace("\n", " ")[:140]
    _log_pass(f"{label} OK | tokens={total_tokens} | response={preview!r}")


async def _run_openai_like_test_with_fallback(
    *,
    candidates: list[tuple[str, str]],
    factory: LLMClientFactory,
) -> None:
    if not candidates:
        raise AssertionError("No OpenAI-compatible provider candidates available.")

    errors: list[str] = []
    for provider, model in candidates:
        try:
            await _run_connection_test(
                label="OpenAI-like",
                provider=provider,
                model=model,
                factory=factory,
            )
            return
        except Exception as exc:  # noqa: BLE001 - fallback should keep trying
            errors.append(f"{provider}: {exc}")
            _log_skip(f"OpenAI-like fallback: {provider} failed, trying next provider")
            continue

    raise AssertionError(f"All OpenAI-like candidates failed: {'; '.join(errors)}")


@tool
class GetWeather(BaseTool):
    """Dummy weather tool for tool-calling validation."""

    city: str

    def run(self) -> str:
        return f"Sunny in {self.city}"

    @classmethod
    def get_name(cls) -> str:
        return "get_weather"


async def _run_tool_call_test(
    *,
    provider: str,
    model: str,
    factory: LLMClientFactory,
) -> None:
    _log_info(f"Tool calling: provider={provider}, model={model}")
    client = factory.get_client(provider)
    adapter = GeminiAdapter() if provider == "gemini" else OpenAIAdapter()
    tool_schema = adapter.export_tool(GetWeather)

    prompts = [
        (
            "What is the weather in London? "
            "Call get_weather exactly once and do not answer from memory."
        ),
        (
            'You must call get_weather with city set to "London". '
            "If you do not call the tool, your answer is wrong."
        ),
    ]

    last_error = "No attempts executed."
    for prompt in prompts:
        response: LLMResponse = await client.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You must call tools when user asks for weather.",
                },
                {"role": "user", "content": prompt},
            ],
            tools=[tool_schema],
            tool_choice="auto",
            temperature=0,
            max_tokens=250,
            model=model,
        )

        _assert(response is not None, "Response must not be None")
        _assert(
            isinstance(response.tool_calls, list), "response.tool_calls must be a list"
        )
        _assert(bool(response.tool_calls), "response.tool_calls must not be empty")

        first_tool_call = response.tool_calls[0]
        converted = adapter.convert_tool_call(first_tool_call)
        tool_name = converted.get("tool_name")
        tool_args = converted.get("inputs", {})
        tool_args_text = json.dumps(tool_args, default=str).lower()

        if tool_name == "get_weather" and "london" in tool_args_text:
            preview = response.content.strip().replace("\n", " ")[:120]
            _log_pass(
                "Tool calling OK | "
                f"tool={tool_name!r} | args={tool_args} | content_preview={preview!r}"
            )
            return

        last_error = (
            f"Got tool_name={tool_name!r}, args={tool_args}. "
            "Expected get_weather with London in args."
        )

    raise AssertionError(last_error)


async def _run_case(
    *,
    label: str,
    counters: Counters,
    strict: bool,
    test_fn: Callable[[], Any],
    skip_reason: Optional[str] = None,
) -> None:
    if skip_reason:
        counters.skipped += 1
        _log_skip(f"{label}: {skip_reason}")
        if strict:
            counters.failed += 1
            _log_fail(f"{label}: strict mode treats skip as failure")
        return

    try:
        await test_fn()
        counters.passed += 1
    except Exception as exc:  # noqa: BLE001 - script should print full failure context
        counters.failed += 1
        _log_fail(f"{label}: {exc}")
        traceback.print_exc()


async def _amain(strict: bool) -> int:
    print("\n=== Xulcan Core Connection Smoke Test ===\n")
    settings = Settings()
    factory = LLMClientFactory(settings)
    counters = Counters()

    openai_like_candidates = _openai_like_candidates(settings)
    gemini_ready = _has_secret(settings.GEMINI_API_KEY)
    tool_choice = _pick_provider_for_tool_test(settings)

    await _run_case(
        label="Test 1 (OpenAI-like provider)",
        counters=counters,
        strict=strict,
        skip_reason=(
            "No OPENAI_API_KEY / DEEPSEEK_API_KEY / OPENROUTER_API_KEY found in environment"
            if not openai_like_candidates
            else None
        ),
        test_fn=lambda: _run_openai_like_test_with_fallback(
            candidates=openai_like_candidates,
            factory=factory,
        ),
    )

    await _run_case(
        label="Test 2 (Gemini provider)",
        counters=counters,
        strict=strict,
        skip_reason=(
            "No GEMINI_API_KEY found in environment" if not gemini_ready else None
        ),
        test_fn=lambda: _run_connection_test(
            label="Gemini",
            provider="gemini",
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            factory=factory,
        ),
    )

    await _run_case(
        label="Test 3 (Tool calling)",
        counters=counters,
        strict=strict,
        skip_reason=(
            "No provider key found for tool calling (OPENROUTER/OPENAI/DEEPSEEK/GEMINI)"
            if tool_choice is None
            else None
        ),
        test_fn=lambda: _run_tool_call_test(
            provider=tool_choice[0] if tool_choice else "",
            model=tool_choice[1] if tool_choice else "",
            factory=factory,
        ),
    )

    print("\n=== Summary ===")
    _log_info(
        f"passed={counters.passed} failed={counters.failed} skipped={counters.skipped}"
    )

    return 1 if counters.failed > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run core LLM smoke tests (provider connections + tool calling)."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat skipped tests as failures.",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(strict=args.strict))


if __name__ == "__main__":
    raise SystemExit(main())
