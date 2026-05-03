"""Unit Tests for xulcan.protocol.io module.

Test Suite Coverage:
    - Class A: UnifiedResponse substantive content validation
    - Class B: Streaming primitives (DeltaContent, UnifiedChunk, deltas)
    - Class C: Integration sanity and sequence logic

Philosophy: Economic Accountability, DoS Prevention, Strict Type Safety.
"""

import pytest
from typing import Any, Dict, List
from pydantic import ValidationError

from xulcan.protocol.io import (
    FinishReason,
    UnifiedResponse,
    FunctionCallDelta,
    ToolCallDelta,
    DeltaContent,
    UnifiedChunk,
)
from xulcan.protocol.tools import ToolCall
from xulcan.protocol.utils import MAX_CHUNK_SIZE
from xulcan.core.economics import UsageStats


# ═══════════════════════════════════════════════════════════════════════════
# ENUM VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestFinishReasonEnum:
    """Validates FinishReason enum values for termination semantics."""

    def test_enum_values_match_protocol(self) -> None:
        """Should have exact string values for wire protocol."""
        assert FinishReason.STOP.value == "stop"
        assert FinishReason.LENGTH.value == "length"
        assert FinishReason.TOOL_CALLS.value == "tool_calls"
        assert FinishReason.CONTENT_FILTER.value == "content_filter"
        assert FinishReason.UNKNOWN.value == "unknown"

    def test_enum_members_are_strings(self) -> None:
        """Should be string enum for JSON serialization."""
        for reason in FinishReason:
            assert isinstance(reason.value, str)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS A: UNIFIED RESPONSE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestUnifiedResponseSubstantiveContent:
    """Validates substantive content enforcement - prevents empty responses."""

    def test_substantive_all_none_fails(self, valid_usage_stats: UsageStats) -> None:
        """Should raise ValidationError if all content fields are None."""
        with pytest.raises(ValidationError) as exc:
            UnifiedResponse(
                content=None,
                reasoning_content=None,
                refusal=None,
                tool_calls=None,
                usage=valid_usage_stats,
                finish_reason=FinishReason.STOP
            )
        
        assert "substantive" in str(exc.value).lower() or "generation failure" in str(exc.value).lower()

    def test_substantive_all_empty_strings_fails(self, valid_usage_stats: UsageStats) -> None:
        """Should raise ValidationError if all content fields are empty strings."""
        with pytest.raises(ValidationError) as exc:
            UnifiedResponse(
                content="",
                reasoning_content="",
                refusal="",
                tool_calls=None,
                usage=valid_usage_stats,
                finish_reason=FinishReason.STOP
            )
        
        assert "substantive" in str(exc.value).lower()

    def test_substantive_all_whitespace_fails(self, valid_usage_stats: UsageStats) -> None:
        """Should raise ValidationError if all content fields are whitespace."""
        with pytest.raises(ValidationError) as exc:
            UnifiedResponse(
                content="   ",
                reasoning_content="  ",
                refusal="    ",
                tool_calls=None,
                usage=valid_usage_stats,
                finish_reason=FinishReason.STOP
            )
        
        assert "substantive" in str(exc.value).lower()

    def test_substantive_empty_tool_calls_list_fails(self, valid_usage_stats: UsageStats) -> None:
        """Should raise ValidationError if tool_calls is empty list with no other content."""
        with pytest.raises(ValidationError) as exc:
            UnifiedResponse(
                content=None,
                reasoning_content=None,
                refusal=None,
                tool_calls=[],
                usage=valid_usage_stats,
                finish_reason=FinishReason.STOP
            )
        
        assert "substantive" in str(exc.value).lower()


class TestUnifiedResponseValidPermutations:
    """Validates all acceptable combinations of substantive content."""

    def test_content_only_succeeds(self, valid_usage_stats: UsageStats) -> None:
        """Should accept response with only content field."""
        response = UnifiedResponse(
            content="The capital of France is Paris.",
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP
        )
        
        assert response.content == "The capital of France is Paris."
        assert response.tool_calls is None
        assert response.refusal is None

    def test_reasoning_content_only_succeeds(self, valid_usage_stats: UsageStats) -> None:
        """Should accept response with only reasoning_content field."""
        response = UnifiedResponse(
            reasoning_content="Let me analyze this step by step...",
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP
        )
        
        assert response.reasoning_content is not None
        assert response.content is None

    def test_refusal_only_succeeds(self, valid_usage_stats: UsageStats) -> None:
        """Should accept response with only refusal field."""
        response = UnifiedResponse(
            refusal="I cannot provide instructions for illegal activities.",
            usage=valid_usage_stats,
            finish_reason=FinishReason.CONTENT_FILTER
        )
        
        assert response.refusal is not None
        assert response.content is None
        assert response.finish_reason == FinishReason.CONTENT_FILTER

    def test_tool_calls_only_succeeds(
        self, 
        valid_usage_stats: UsageStats, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept response with only tool_calls field."""
        response = UnifiedResponse(
            tool_calls=[valid_tool_call],
            usage=valid_usage_stats,
            finish_reason=FinishReason.TOOL_CALLS
        )
        
        assert len(response.tool_calls) == 1
        assert response.content is None
        assert response.finish_reason == FinishReason.TOOL_CALLS

    def test_content_and_tool_calls_succeeds(
        self, 
        valid_usage_stats: UsageStats, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept response with both content and tool_calls."""
        response = UnifiedResponse(
            content="Let me search for that information.",
            tool_calls=[valid_tool_call],
            usage=valid_usage_stats,
            finish_reason=FinishReason.TOOL_CALLS
        )
        
        assert response.content is not None
        assert len(response.tool_calls) == 1

    def test_all_fields_populated_succeeds(
        self, 
        valid_usage_stats: UsageStats, 
        valid_tool_call: ToolCall
    ) -> None:
        """Should accept response with all content fields populated."""
        response = UnifiedResponse(
            content="Main response",
            reasoning_content="Internal thoughts",
            tool_calls=[valid_tool_call],
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP
        )
        
        assert response.content is not None
        assert response.reasoning_content is not None
        assert response.tool_calls is not None


class TestUnifiedResponseStructure:
    """Validates UnifiedResponse field constraints and types."""

    def test_finish_reason_constraints(self, valid_usage_stats: UsageStats) -> None:
        """Should enforce literal finish_reason values."""
        with pytest.raises(ValidationError):
            UnifiedResponse(
                content="Test",
                usage=valid_usage_stats,
                finish_reason="invalid_reason"  # type: ignore
            )

    @pytest.mark.parametrize("reason", [
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.TOOL_CALLS,
        FinishReason.CONTENT_FILTER,
        FinishReason.UNKNOWN,
    ])
    def test_finish_reason_valid_values(
        self, 
        valid_usage_stats: UsageStats,
        reason: FinishReason
    ) -> None:
        """Should accept all valid finish_reason values."""
        response = UnifiedResponse(
            content="Test",
            usage=valid_usage_stats,
            finish_reason=reason
        )
        assert response.finish_reason == reason

    def test_usage_is_mandatory(self) -> None:
        """Should require usage field for economic accountability."""
        with pytest.raises(ValidationError):
            UnifiedResponse(
                content="Test response",
                finish_reason=FinishReason.STOP
                # Missing usage
            )


    def test_provider_metadata_defaults_to_empty_dict(
        self, 
        valid_usage_stats
    ) -> None:
        """Should initialize provider_metadata as empty dict."""
        
        response = UnifiedResponse(
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP, # O "stop"
            content="test" 
        )

        assert response.provider_metadata == {}
        assert isinstance(response.provider_metadata, dict)

    def test_provider_metadata_accepts_custom_values(
        self, 
        valid_usage_stats: UsageStats, 
        mock_provider_metadata: Dict[str, Any]
    ) -> None:
        """Should accept custom provider metadata."""
        response = UnifiedResponse(
            content="Test",
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP,
            provider_metadata=mock_provider_metadata
        )
        
        assert response.provider_metadata == mock_provider_metadata

    def test_logprobs_optional(self, valid_unified_response: UnifiedResponse) -> None:
        """Should allow logprobs to be None."""
        assert valid_unified_response.logprobs is None

    def test_logprobs_accepts_list(self, valid_usage_stats: UsageStats) -> None:
        """Should accept list of log probability dictionaries."""
        logprobs = [
            {"token": "The", "logprob": -0.5},
            {"token": " capital", "logprob": -1.2}
        ]
        
        response = UnifiedResponse(
            content="The capital",
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP,
            logprobs=logprobs
        )
        
        assert response.logprobs == logprobs


# ═══════════════════════════════════════════════════════════════════════════
# CLASS B: STREAMING PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

class TestFunctionCallDelta:
    """Validates partial function call fragment structure."""

    def test_all_fields_optional(self) -> None:
        """Should allow all fields to be None for incremental updates."""
        delta = FunctionCallDelta()
        
        assert delta.name is None
        assert delta.arguments is None

    def test_name_only(self, valid_machine_id: str) -> None:
        """Should accept only name field."""
        delta = FunctionCallDelta(name=valid_machine_id)
        
        assert delta.name == valid_machine_id
        assert delta.arguments is None

    def test_arguments_only(self) -> None:
        """Should accept only arguments field."""
        delta = FunctionCallDelta(arguments='{"city":')
        
        assert delta.name is None
        assert delta.arguments == '{"city":'

    def test_accepts_incomplete_json(self) -> None:
        """Should accept incomplete JSON in arguments for streaming."""
        incomplete_json = '{"location": "San'
        delta = FunctionCallDelta(arguments=incomplete_json)
        
        assert delta.arguments == incomplete_json


class TestToolCallDelta:
    """Validates partial tool call structure with mandatory index."""

    def test_index_mandatory(self) -> None:
        """Should require index field for correlation."""
        with pytest.raises(ValidationError):
            ToolCallDelta()  # Missing index

    def test_minimal_valid_structure(self) -> None:
        """Should accept only index field."""
        delta = ToolCallDelta(index=0)
        
        assert delta.index == 0
        assert delta.id is None
        assert delta.type is None
        assert delta.function is None

    def test_first_chunk_with_id(self, valid_tool_id: str) -> None:
        """Should accept first chunk with id and type."""
        delta = ToolCallDelta(
            index=0,
            id=valid_tool_id,
            type="function"
        )
        
        assert delta.index == 0
        assert delta.id == valid_tool_id
        assert delta.type == "function"

    def test_partial_function_name(self, valid_machine_id: str) -> None:
        """Should accept partial function call with only name."""
        delta = ToolCallDelta(
            index=0,
            function=FunctionCallDelta(name=valid_machine_id)
        )
        
        assert delta.function.name == valid_machine_id
        assert delta.function.arguments is None

    def test_partial_function_arguments(self) -> None:
        """Should accept partial function call with only arguments."""
        delta = ToolCallDelta(
            index=0,
            function=FunctionCallDelta(arguments='{"q":')
        )
        
        assert delta.function.name is None
        assert delta.function.arguments == '{"q":'

    def test_multiple_indices_for_parallel_calls(
        self, 
        valid_tool_id: str
    ) -> None:
        """Should support multiple tool calls via different indices."""
        delta1 = ToolCallDelta(index=0, id=f"{valid_tool_id}_1")
        delta2 = ToolCallDelta(index=1, id=f"{valid_tool_id}_2")
        
        assert delta1.index == 0
        assert delta2.index == 1


class TestDeltaContentStructure:
    """Validates incremental content update structure."""

    def test_all_fields_optional(self) -> None:
        """Should allow empty delta for accumulation."""
        delta = DeltaContent()
        
        assert delta.content is None
        assert delta.reasoning_content is None
        assert delta.tool_calls is None
        assert delta.refusal is None

    def test_content_only(self) -> None:
        """Should accept only content field."""
        delta = DeltaContent(content="Hello")
        
        assert delta.content == "Hello"
        assert delta.reasoning_content is None

    def test_reasoning_content_only(self) -> None:
        """Should accept only reasoning_content field."""
        delta = DeltaContent(reasoning_content="Analyzing...")
        
        assert delta.reasoning_content == "Analyzing..."
        assert delta.content is None

    def test_tool_calls_with_delta_objects(self, valid_tool_id: str) -> None:
        """Should accept list of ToolCallDelta objects."""
        tool_deltas = [
            ToolCallDelta(index=0, id=valid_tool_id, type="function")
        ]
        
        delta = DeltaContent(tool_calls=tool_deltas)
        
        assert len(delta.tool_calls) == 1
        assert isinstance(delta.tool_calls[0], ToolCallDelta)

    def test_refusal_only(self) -> None:
        """Should accept only refusal field."""
        delta = DeltaContent(refusal="I cannot ")
        
        assert delta.refusal == "I cannot "


class TestDeltaContentDoSProtection:
    """Validates chunk size limits to prevent memory exhaustion attacks."""

    def test_content_within_limit(self) -> None:
        """Should accept content within MAX_CHUNK_SIZE."""
        safe_content = "x" * (MAX_CHUNK_SIZE // 2)
        delta = DeltaContent(content=safe_content)
        
        assert len(delta.content) == MAX_CHUNK_SIZE // 2

    def test_content_exceeds_limit_fails(self) -> None:
        """Should raise ValidationError if content exceeds MAX_CHUNK_SIZE."""
        oversized_content = "x" * (MAX_CHUNK_SIZE + 1)
        
        with pytest.raises(ValidationError) as exc:
            DeltaContent(content=oversized_content)
        
        assert "exceeds safety limit" in str(exc.value).lower() or "dos" in str(exc.value).lower()

    def test_combined_fields_exceed_limit_fails(self) -> None:
        """Should raise ValidationError if combined fields exceed limit."""
        half_size = (MAX_CHUNK_SIZE // 2) + 1
        
        with pytest.raises(ValidationError) as exc:
            DeltaContent(
                content="x" * half_size,
                reasoning_content="y" * half_size
            )
        
        assert "exceeds safety limit" in str(exc.value).lower()

    def test_refusal_within_limit(self) -> None:
        """Should accept refusal within limit."""
        safe_refusal = "Sorry. " * 100
        delta = DeltaContent(refusal=safe_refusal)
        
        assert delta.refusal is not None


class TestUnifiedChunkStructure:
    """Validates streaming event structure and finalization."""

    def test_minimal_chunk_with_delta(self) -> None:
        """Should accept chunk with only delta field."""
        chunk = UnifiedChunk(
            delta=DeltaContent(content="Hello")
        )
        
        assert chunk.delta.content == "Hello"
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_regular_chunk_without_termination(self) -> None:
        """Should accept regular chunk with content delta."""
        chunk = UnifiedChunk(
            delta=DeltaContent(content=" world"),
            id="chunk_2"
        )
        
        assert chunk.delta.content == " world"
        assert chunk.finish_reason is None

    def test_final_chunk_with_finish_reason(self, valid_usage_stats: UsageStats) -> None:
        """Should accept final chunk with termination metadata."""
        chunk = UnifiedChunk(
            delta=DeltaContent(),
            finish_reason=FinishReason.STOP,
            usage=valid_usage_stats,
            id="chunk_final"
        )
        
        assert chunk.finish_reason == FinishReason.STOP
        assert chunk.usage is not None

    def test_chunk_with_id(self) -> None:
        """Should accept provider-assigned chunk identifier."""
        chunk = UnifiedChunk(
            delta=DeltaContent(content="test"),
            id="chunk_abc_123"
        )
        
        assert chunk.id == "chunk_abc_123"

    def test_provider_metadata_defaults_empty(
        self, 
        valid_unified_chunk_delta: UnifiedChunk
    ) -> None:
        """Should initialize provider_metadata as empty dict."""
        assert valid_unified_chunk_delta.provider_metadata == {}

    def test_logprobs_in_chunk(self) -> None:
        """Should accept log probabilities for chunk tokens."""
        logprobs = [{"token": "Hello", "logprob": -0.3}]
        
        chunk = UnifiedChunk(
            delta=DeltaContent(content="Hello"),
            logprobs=logprobs
        )
        
        assert chunk.logprobs == logprobs


class TestUnifiedChunkMetadataSafety:
    """Validates metadata recursion depth limits (DoS prevention)."""

    def test_metadata_accepts_flat_structure(self) -> None:
        """Should accept flat metadata dictionary."""
        metadata = {
            "chunk_index": 5,
            "timestamp": "2024-01-01T00:00:00Z",
            "model_version": "v1.2.3"
        }
        
        chunk = UnifiedChunk(
            delta=DeltaContent(content="test"),
            provider_metadata=metadata
        )
        
        assert chunk.provider_metadata == metadata

    def test_metadata_rejects_excessive_nesting(self) -> None:
        """Should raise ValidationError for deeply nested metadata."""
        # Create deeply nested structure
        deep_metadata: Dict[str, Any] = {"level": 0}
        current = deep_metadata
        
        for i in range(1, 50):  # Exceed reasonable depth
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(ValidationError) as exc:
            UnifiedChunk(
                delta=DeltaContent(content="test"),
                provider_metadata=deep_metadata
            )
        
        assert "recursion" in str(exc.value).lower() or "depth" in str(exc.value).lower()

    def test_metadata_rejects_circular_references(self) -> None:
        """Should raise ValidationError for circular metadata references."""
        circular_metadata: Dict[str, Any] = {}
        circular_metadata["self"] = circular_metadata
        
        with pytest.raises(ValidationError):
            UnifiedChunk(
                delta=DeltaContent(content="test"),
                provider_metadata=circular_metadata
            )


# ═══════════════════════════════════════════════════════════════════════════
# CLASS C: INTEGRATION SANITY
# ═══════════════════════════════════════════════════════════════════════════

class TestStreamingSequenceLogic:
    """Validates that streaming components can coexist in logical sequences."""

    def test_chunk_sequence_validates_individually(
        self, 
        valid_usage_stats: UsageStats,
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should validate each chunk in a realistic streaming sequence."""
        # Chunk 1: Start of content
        chunk1 = UnifiedChunk(
            delta=DeltaContent(content="The capital"),
            id="chunk_1"
        )
        assert chunk1.delta.content is not None
        
        # Chunk 2: Continue content
        chunk2 = UnifiedChunk(
            delta=DeltaContent(content=" of France"),
            id="chunk_2"
        )
        assert chunk2.delta.content is not None
        
        # Chunk 3: Tool call initiation
        chunk3 = UnifiedChunk(
            delta=DeltaContent(
                tool_calls=[
                    ToolCallDelta(index=0, id=valid_tool_id, type="function")
                ]
            ),
            id="chunk_3"
        )
        assert len(chunk3.delta.tool_calls) == 1
        
        # Chunk 4: Tool call function name
        chunk4 = UnifiedChunk(
            delta=DeltaContent(
                tool_calls=[
                    ToolCallDelta(
                        index=0,
                        function=FunctionCallDelta(name=valid_machine_id)
                    )
                ]
            ),
            id="chunk_4"
        )
        assert chunk4.delta.tool_calls[0].function.name == valid_machine_id
        
        # Chunk 5: Final chunk with termination
        chunk5 = UnifiedChunk(
            delta=DeltaContent(),
            finish_reason=FinishReason.TOOL_CALLS,
            usage=valid_usage_stats,
            id="chunk_final"
        )
        assert chunk5.finish_reason == FinishReason.TOOL_CALLS
        assert chunk5.usage is not None

    def test_mixed_content_and_reasoning_stream(self) -> None:
        """Should handle interleaved content and reasoning chunks."""
        # Content chunk
        chunk1 = UnifiedChunk(
            delta=DeltaContent(content="Let me think...")
        )
        assert chunk1.delta.content is not None
        
        # Reasoning chunk
        chunk2 = UnifiedChunk(
            delta=DeltaContent(reasoning_content="Step 1: Analyze...")
        )
        assert chunk2.delta.reasoning_content is not None
        
        # More content
        chunk3 = UnifiedChunk(
            delta=DeltaContent(content=" The answer is 42.")
        )
        assert chunk3.delta.content is not None

    def test_refusal_stream(self, valid_usage_stats: UsageStats) -> None:
        """Should handle streaming refusal content."""
        # Start refusal
        chunk1 = UnifiedChunk(
            delta=DeltaContent(refusal="I cannot provide")
        )
        
        # Continue refusal
        chunk2 = UnifiedChunk(
            delta=DeltaContent(refusal=" instructions for")
        )
        
        # Complete refusal
        chunk3 = UnifiedChunk(
            delta=DeltaContent(refusal=" illegal activities."),
            finish_reason=FinishReason.CONTENT_FILTER,
            usage=valid_usage_stats
        )
        
        assert chunk3.finish_reason == FinishReason.CONTENT_FILTER


class TestEdgeCasesAndBoundaries:
    """Validates edge cases and boundary conditions."""

    def test_empty_string_vs_none_in_response(self, valid_usage_stats: UsageStats) -> None:
        """Should treat empty string differently from None."""
        # None is acceptable if other fields have content
        response1 = UnifiedResponse(
            content=None,
            reasoning_content="Thinking...",
            usage=valid_usage_stats,
            finish_reason=FinishReason.STOP
        )
        assert response1.content is None
        
        # Empty string should fail validation
        with pytest.raises(ValidationError):
            UnifiedResponse(
                content="",
                reasoning_content=None,
                refusal=None,
                tool_calls=None,
                usage=valid_usage_stats,
                finish_reason=FinishReason.STOP
            )

    def test_tool_call_delta_with_zero_index(self) -> None:
        """Should accept index=0 as valid."""
        delta = ToolCallDelta(index=0)
        assert delta.index == 0

    def test_chunk_with_empty_delta(self) -> None:
        """Should accept chunk with empty delta."""
        chunk = UnifiedChunk(delta=DeltaContent())
        assert chunk.delta is not None

    def test_usage_stats_in_non_final_chunk(self, valid_usage_stats: UsageStats) -> None:
        """Should accept usage stats in non-final chunks (though atypical)."""
        chunk = UnifiedChunk(
            delta=DeltaContent(content="test"),
            usage=valid_usage_stats
            # No finish_reason - not technically final
        )
        
        assert chunk.usage is not None
        assert chunk.finish_reason is None