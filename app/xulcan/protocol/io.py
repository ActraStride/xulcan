"""
Output contracts for model generation responses.

This module defines the response formats returned by the Kernel after model
generation completes. It supports both synchronous (complete) and streaming
(incremental) response modes, with strict validation to prevent protocol
violations and ensure economic accountability.

Response Types:
    - UnifiedResponse: Complete, finalized response from synchronous generation.
    - DeltaContent: Incremental update in a streaming response.
    - UnifiedChunk: Single event in a streaming response sequence.

Security Features:
    - Substantive content validation rejects empty responses.
    - Chunk size limits prevent DoS via memory exhaustion.
    - Usage statistics enforce economic accountability.

Enums:
    FinishReason: Enumerates why a model generation terminated.
"""

from __future__ import annotations

from typing import Literal
from enum import Enum

from pydantic import Field, model_validator

from xulcan.core.primitives import (
    ImmutableRecord,
    SemanticText,
    JsonDict
)

from xulcan.core.economics import UsageStats

from .tools import ToolCall
from .utils import MAX_CHUNK_SIZE


# =============================================================================
# DOMAIN ENUMERATIONS
# =============================================================================

class FinishReason(str, Enum):
    """Enumerates why a model generation terminated.

    Used for telemetry, debugging, and enforcing correct handling of incomplete
    responses (e.g., length limits require continuation logic).

    Attributes:
        STOP: Natural completion (model satisfied the request).
        LENGTH: Hit token/character limit (response may be truncated).
        TOOL_CALLS: Model delegated to external tools (requires continuation).
        CONTENT_FILTER: Safety filter triggered (response blocked).
        UNKNOWN: Fallback for provider-specific reasons.
    """
    STOP = "stop"                    # Natural completion
    LENGTH = "length"                # Hit token/character limit
    TOOL_CALLS = "tool_calls"        # Model requested tool execution
    CONTENT_FILTER = "content_filter"  # Safety filter triggered
    UNKNOWN = "unknown"              # Fallback for provider-specific reasons


# =============================================================================
# RESPONSE PRIMITIVES (Complete Generations)
# =============================================================================

class UnifiedResponse(ImmutableRecord):
    """A complete, finalized response from a model generation request.

    This is the terminal output type returned after a full generation completes
    (non-streaming mode). It aggregates all response components—text, tool calls,
    reasoning, refusals—along with resource consumption metrics and termination
    metadata.

    Economic Accounting:
        The 'usage' field tracks the actual resource consumption (tokens) for
        billing, rate limiting, and capacity planning. Providers must report
        accurate counts to prevent resource leakage.

    Finish Reason Semantics:
        - "stop": Natural completion (model satisfied the request).
        - "length": Hit token/character limit (response may be truncated).
        - "tool_calls": Model delegated to external tools (requires continuation).
        - "content_filter": Safety system blocked the response.
        - "unknown": Fallback for provider-specific reasons.

    Attributes:
        content: Main response text visible to users.
        reasoning_content: Internal reasoning steps (extended thinking).
        refusal: Refusal explanation (if model declined).
        tool_calls: Requested tool invocations.
        usage: Token consumption statistics (input + output + total).
        finish_reason: Why the generation terminated.
        provider_metadata: Provider-specific metadata (model version, headers).
        logprobs: Log probabilities for generated tokens (debugging/analysis).
    """
    content: SemanticText | None = Field(
        default=None,
        description="Main response text visible to end-users."
    )

    reasoning_content: SemanticText | None = Field(
        default=None,
        description="Internal chain-of-thought steps (not shown to users)."
    )

    refusal: SemanticText | None = Field(
        default=None,
        description="Explanation of why the model declined to respond."
    )

    tool_calls: list[ToolCall] | None = Field(
        default=None,
        description="Tool invocations requested by the model."
    )

    usage: UsageStats = Field(
        description="Token consumption metrics for economic accounting and rate limiting."
    )

    finish_reason: FinishReason = Field(
        description="Reason the generation terminated (affects continuation logic)."
    )

    provider_metadata: JsonDict = Field(
        default_factory=dict,
        description="Provider-specific metadata (model version, request headers, etc.)."
    )

    logprobs: list[JsonDict] | None = Field(
        default=None,
        description="Log probabilities for generated tokens (debugging and analysis)."
    )

    @model_validator(mode='after')
    def validate_has_content(self) -> UnifiedResponse:
        """Ensures the response contains substantive data.

        A response without content represents a generation failure. This could
        indicate a provider bug, timeout, or safety filter activation. At least
        one of the content fields must be populated.

        Returns:
            UnifiedResponse: The validated instance.

        Raises:
            ValueError: If all content fields are empty or None.
        """
        has_content = bool(self.content and self.content.strip())
        has_reasoning = bool(self.reasoning_content and self.reasoning_content.strip())
        has_refusal = bool(self.refusal and self.refusal.strip())
        has_tool_calls = bool(self.tool_calls)

        if not any([has_content, has_reasoning, has_refusal, has_tool_calls]):
            raise ValueError(
                "UnifiedResponse must contain substantive data in at least one field. "
                "Received: content={}, reasoning_content={}, refusal={}, tool_calls={}. "
                "This indicates a generation failure or corrupted provider response.".format(
                    repr(self.content),
                    repr(self.reasoning_content),
                    repr(self.refusal),
                    repr(self.tool_calls)
                )
            )

        return self


# =============================================================================
# STREAMING PRIMITIVES (Incremental Updates)
# =============================================================================

class FunctionCallDelta(ImmutableRecord):
    """Partial function invocation data within a streaming chunk.

    Attributes:
        name: Partial function name (may be split across multiple chunks).
        arguments: Partial JSON string of arguments (must be concatenated, invalid JSON until complete).
    """

    name: str | None = Field(
        default=None,
        description="Partial function name (may be split across multiple chunks)."
    )
    arguments: str | None = Field(
        default=None,
        description="Partial JSON string of arguments (must be concatenated, invalid JSON until complete)."
    )


class ToolCallDelta(ImmutableRecord):
    """Partial tool call object within a streaming chunk.

    Attributes:
        index: Position in the tool calls array. Vital for merging concurrent tool call streams.
        id: Provider-assigned tool call ID (usually present only in the first chunk).
        type: Tool type discriminator.
        function: Partial function invocation data.
    """

    index: int = Field(
        description="Position in the tool calls array. Vital for merging concurrent tool call streams."
    )
    id: str | None = Field(
        default=None,
        description="Provider-assigned tool call ID (usually present only in the first chunk)."
    )
    type: Literal["function"] | None = Field(
        default=None,
        description="Tool type discriminator."
    )
    function: FunctionCallDelta | None = Field(
        default=None,
        description="Partial function invocation data."
    )


class DeltaContent(ImmutableRecord):
    """Represents an incremental update in a streaming response.

    Streaming responses are delivered as a sequence of delta chunks, each
    containing a partial string or object. The client must accumulate deltas
    to reconstruct the complete response.

    Accumulation Strategy:
        - Strings (content, reasoning_content, refusal): Concatenate.
        - Tool calls: Merge partial objects by index, handling incomplete JSON.

    Attributes:
        content: Partial response text (accumulate via concatenation).
        reasoning_content: Partial reasoning steps (accumulate via concatenation).
        refusal: Partial refusal explanation (accumulate via concatenation).
        tool_calls: Partial tool call objects (may be incomplete until final chunk).
    """
    content: str | None = Field(
        default=None,
        description="Partial response text (accumulate via concatenation)."
    )

    reasoning_content: str | None = Field(
        default=None,
        description="Partial reasoning steps (accumulate via concatenation)."
    )

    tool_calls: list[ToolCallDelta] | None = Field(
        default=None,
        description="Partial tool call objects (may be incomplete until final chunk)."
    )

    refusal: str | None = Field(
        default=None,
        description="Partial refusal explanation (accumulate via concatenation)."
    )

    @model_validator(mode='after')
    def validate_chunk_size(self) -> DeltaContent:
        """Prevents DoS via memory exhaustion from massive chunks.

        Streaming chunks should be small increments. A chunk exceeding the limit
        is indistinguishable from an attack or a provider malfunction.

        Returns:
            DeltaContent: The validated instance.

        Raises:
            ValueError: If the total character count exceeds MAX_CHUNK_SIZE.
        """
        # Note: We use character count as a fast O(1) proxy for byte size
        # to avoid O(N) UTF-8 encoding overhead during a potential DoS attack.
        total_size = 0
        if self.content:
            total_size += len(self.content)
        if self.reasoning_content:
            total_size += len(self.reasoning_content)
        if self.refusal:
            total_size += len(self.refusal)

        if total_size > MAX_CHUNK_SIZE:
            raise ValueError(
                f"Chunk size ({total_size} chars) exceeds safety limit of {MAX_CHUNK_SIZE}. "
                "This serves as a DoS protection against malicious streams."
            )

        return self


class UnifiedChunk(ImmutableRecord):
    """Represents a single event in a streaming response sequence.

    Analogous to a Server-Sent Event (SSE). Streaming responses consist of
    multiple chunks, with the final chunk typically containing the finish_reason
    and usage statistics.

    Chunk Types:
        - Regular chunk: Contains delta with partial content.
        - Final chunk: Contains finish_reason and usage (may have empty delta).

    Attributes:
        delta: Incremental content update (accumulate with previous deltas).
        finish_reason: Present only in the final chunk; signals stream termination.
        usage: Token usage statistics (present only in the final chunk).
        id: Provider-assigned chunk identifier for debugging and correlation.
        provider_metadata: Provider-specific streaming metadata (chunk index, timestamps).
        logprobs: Log probabilities for tokens generated in this chunk.
    """
    delta: DeltaContent = Field(
        description="Incremental content update (accumulate with previous deltas)."
    )

    finish_reason: FinishReason | None = Field(
        default=None,
        description="Present only in the final chunk; signals stream termination."
    )

    usage: UsageStats | None = Field(
        default=None,
        description="Token usage statistics (present only in the final chunk)."
    )

    id: str | None = Field(
        default=None,
        description="Provider-assigned chunk identifier for debugging and correlation."
    )

    provider_metadata: JsonDict = Field(
        default_factory=dict,
        description="Provider-specific streaming metadata (chunk index, timestamps)."
    )

    logprobs: list[JsonDict] | None = Field(
        default=None,
        description="Log probabilities for tokens generated in this chunk."
    )
