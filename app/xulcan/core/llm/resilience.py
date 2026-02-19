"""Fallback client for trying more than one provider.

Use this when you want provider A first, then provider B if A fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from xulcan.core.llm.client import (
    BaseLLMClient,
    LLMAuthenticationError,
    LLMClientFactory,
    LLMProviderError,
    LLMResponse,
    LLMValidationError,
)


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    model: Optional[str] = None


class AllProvidersFailedError(Exception):
    """Raised when all configured provider attempts fail."""

    def __init__(self, providers: Sequence[str], errors: Sequence[str]) -> None:
        self.providers = list(providers)
        self.errors = list(errors)
        detail = "; ".join(self.errors) if self.errors else "No provider details."
        super().__init__(f"All provider attempts failed: {detail}")


class ResilientClient(BaseLLMClient):
    """Try providers in order until one succeeds."""

    def __init__(
        self,
        factory: LLMClientFactory,
        candidates: Sequence[ProviderCandidate | str],
    ) -> None:
        self.factory = factory
        self.candidates = [
            self._normalize_candidate(candidate) for candidate in candidates
        ]

    @staticmethod
    def _normalize_candidate(candidate: ProviderCandidate | str) -> ProviderCandidate:
        if isinstance(candidate, str):
            return ProviderCandidate(provider=candidate)
        return candidate

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
        attempted: List[str] = []
        errors: List[str] = []

        for candidate in self.candidates:
            provider = candidate.provider
            attempted.append(provider)

            try:
                client = self.factory.get_client(provider)
                response = await client.create_chat_completion(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=candidate.model or model,
                )
                return response
            except (
                LLMProviderError,
                LLMValidationError,
                LLMAuthenticationError,
            ) as exc:
                errors.append(f"{provider}: {exc}")
                continue

        raise AllProvidersFailedError(providers=attempted, errors=errors)
