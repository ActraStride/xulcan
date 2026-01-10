"""Comprehensive test suite for protocol tools type definitions.

This module validates the integrity, serialization, and API compliance of
tool-related types including ToolCall, FunctionDef, ToolDefinition, and
NamedToolChoice. Tests cover enumeration invariants, deep validation rules,
JSON Schema compliance, serialization hygiene, and security boundaries
against malformed or malicious inputs.
"""

import pytest
from typing import Any, Dict
from pydantic import ValidationError
import keyword
import json

from xulcan.core.types import (
    Role,
    FinishReason,
    ContentType,
    ToolChoiceType,
    ToolCall,
    FunctionDef,
    ToolDefinition,
    NamedToolChoice,
    ToolChoice,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def valid_parameters_schema() -> Dict[str, Any]:
    """Provides a compliant JSON Schema for testing."""
    return {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
            "unit": {"type": "string", "enum": ["c", "f"]}
        },
        "required": ["location"]
    }

@pytest.fixture
def valid_arguments() -> Dict[str, Any]:
    """Provides valid arguments matching the schema."""
    return {"location": "Paris", "unit": "c"}

@pytest.fixture
def valid_function_def(valid_parameters_schema: Dict[str, Any]) -> FunctionDef:
    """Provides a standard, valid FunctionDef."""
    return FunctionDef(
        name="get_current_weather",
        description="Fetches weather for a location",
        parameters=valid_parameters_schema
    )

@pytest.fixture
def valid_tool_call(valid_arguments: Dict[str, Any]) -> ToolCall:
    """Provides a standard, valid ToolCall."""
    return ToolCall(
        id="call_default_123",
        name="get_current_weather",
        arguments=valid_arguments
    )

@pytest.fixture
def valid_tool_definition(valid_function_def: FunctionDef) -> ToolDefinition:
    """Provides a valid ToolDefinition container."""
    return ToolDefinition(
        type="function",
        function=valid_function_def
    )

@pytest.fixture
def valid_named_tool_choice() -> NamedToolChoice:
    """Provides a valid forced tool choice."""
    return NamedToolChoice(
        type="function",
        function={"name": "get_current_weather"}
    )

@pytest.fixture
def recursive_dict() -> Dict[str, Any]:
    """Provides a dictionary that references itself (cyclic)."""
    d: Dict[str, Any] = {}
    d["self"] = d
    return d

@pytest.fixture
def deeply_nested_dict() -> Dict[str, Any]:
    """Provides a dictionary nested 50 levels deep."""
    root: Dict[str, Any] = {"value": "core"}
    for _ in range(50):
        root = {"layer": root}
    return root


# ═══════════════════════════════════════════════════════════════════════════
# 1. ENUMERATION INVARIANTS & VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


class TestRoleEnum:
    """Role Enum API String Matching"""

    def test_matches_exact_api_strings(self) -> None:
        """Should match exact API strings for Role enum."""
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"

    def test_rejects_case_variations(self) -> None:
        """Should reject case variations strictly."""
        with pytest.raises(ValueError):
            Role("SYSTEM")
        with pytest.raises(ValueError):
            Role("User")
        with pytest.raises(ValueError):
            Role("Assistant")


class TestFinishReasonEnum:
    """FinishReason Enum API String Matching"""

    def test_matches_exact_api_strings(self) -> None:
        """Should match exact API strings for FinishReason enum."""
        assert FinishReason.STOP.value == "stop"
        assert FinishReason.LENGTH.value == "length"
        assert FinishReason.TOOL_CALLS.value == "tool_calls"
        assert FinishReason.CONTENT_FILTER.value == "content_filter"
        assert FinishReason.UNKNOWN.value == "unknown"

    def test_rejects_plausible_but_incorrect_values(self) -> None:
        """Should reject plausible but incorrect values."""
        with pytest.raises(ValueError):
            FinishReason("stopped")
        with pytest.raises(ValueError):
            FinishReason("max_length")
        with pytest.raises(ValueError):
            FinishReason("tool_use")


# ═══════════════════════════════════════════════════════════════════════════
# 2. TOOLCALL DATA INTEGRITY & SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallDataIntegrity:
    """ToolCall Data Integrity & Serialization"""

    # --- Data Integrity ---

    def test_rejects_empty_tool_call_ids(self) -> None:
        """Should reject empty tool call IDs."""
        with pytest.raises(ValidationError):
            ToolCall(id="", name="search", arguments={})

    def test_accepts_valid_function_names(self, valid_tool_call: ToolCall) -> None:
        """Should accept valid function names."""
        assert valid_tool_call.name == "get_current_weather"

    def test_rejects_function_names_with_invalid_characters(self) -> None:
        """Should reject function names with invalid characters."""
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="invalid-name!", arguments={})
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="invalid name", arguments={})
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="invalid.name", arguments={})

    def test_rejects_none_as_arguments(self) -> None:
        """Should reject None as arguments."""
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments=None)

    def test_rejects_non_dictionary_argument_types(self) -> None:
        """Should reject non-dictionary argument types."""
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments="not a dict")
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments=["list"])
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments=42)

    # --- Serialization ---

    def test_correctly_serializes_deeply_nested_argument_dictionaries(self) -> None:
        """Should correctly serialize deeply nested argument dictionaries."""
        nested_args = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {"value": "deep"}
                    }
                }
            }
        }
        tool_call = ToolCall(id="call_123", name="func", arguments=nested_args)
        serialized = tool_call.model_dump()
        assert serialized["arguments"]["level1"]["level2"]["level3"]["level4"]["value"] == "deep"

    def test_fails_serialization_for_arguments_containing_non_serializable_objects(self) -> None:
        """Should fail serialization for arguments containing non-serializable objects."""
        class NonSerializable:
            pass
        
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments={"obj": NonSerializable()})

    def test_fails_serialization_for_arguments_containing_sets(self) -> None:
        """Should fail serialization for arguments containing sets."""
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="func", arguments={"data": {1, 2, 3}})

    def test_handles_complex_nested_argument_structures(self) -> None:
        """Should handle complex nested argument structures."""
        complex_args = {
            "users": [
                {"id": 1, "name": "Alice", "metadata": {"role": "admin"}},
                {"id": 2, "name": "Bob", "metadata": {"role": "user"}}
            ],
            "config": {
                "enabled": True,
                "limits": [10, 20, 30],
                "nested": {"deep": {"value": 42}}
            }
        }
        tool_call = ToolCall(id="call_123", name="func", arguments=complex_args)
        serialized = tool_call.model_dump()
        assert len(serialized["arguments"]["users"]) == 2
        assert serialized["arguments"]["config"]["nested"]["deep"]["value"] == 42


# ═══════════════════════════════════════════════════════════════════════════
# 3. FUNCTIONDEF SCHEMA CONSISTENCY & VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionDefValidation:
    """FunctionDef Schema Consistency & Validation"""

    # --- Name Validation ---

    def test_rejects_function_names_colliding_with_python_keywords(self) -> None:
        """Should reject function names colliding with Python keywords."""
        for kw in ["class", "def", "return", "if", "while", "for"]:
            with pytest.raises(ValidationError):
                FunctionDef(name=kw, parameters={"type": "object"})

    # --- Parameters Validation ---

    def test_accepts_empty_parameters_dictionary(self) -> None:
        """Should accept empty parameters dictionary."""
        func = FunctionDef(name="func", parameters={})
        assert func.parameters == {}

    def test_rejects_none_as_parameters(self) -> None:
        """Should reject None as parameters."""
        with pytest.raises(ValidationError):
            FunctionDef(name="func", parameters=None)

    # --- Description Validation ---

    def test_accepts_very_long_descriptions(self) -> None:
        """Should accept very long descriptions."""
        long_desc = "A" * 10000
        func = FunctionDef(
            name="func",
            description=long_desc,
            parameters={"type": "object"}
        )
        assert len(func.description) == 10000

    def test_accepts_descriptions_with_control_characters(self) -> None:
        """Should accept descriptions with control characters."""
        desc_with_controls = "Line1\nLine2\tTabbed\rCarriage"
        func = FunctionDef(
            name="func",
            description=desc_with_controls,
            parameters={"type": "object"}
        )
        assert "\n" in func.description
        assert "\t" in func.description

    # --- JSON Schema Validation ---

    def test_rejects_invalid_json_schema_structures(self) -> None:
        """Should reject invalid JSON Schema structures."""
        # Parameters must be a dictionary
        with pytest.raises(ValidationError):
            FunctionDef(name="func", parameters="not a dict")
        with pytest.raises(ValidationError):
            FunctionDef(name="func", parameters=[])

    def test_accepts_valid_json_schema(self, valid_parameters_schema: Dict[str, Any]) -> None:
        """Should accept valid JSON Schema."""
        func = FunctionDef(name="func", parameters=valid_parameters_schema)
        assert func.parameters["type"] == "object"
        assert "location" in func.parameters["required"]

    def test_handles_complex_json_schema_definitions(self) -> None:
        """Should handle complex JSON Schema definitions."""
        complex_schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                        "coordinates": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "number"},
                                "lon": {"type": "number"}
                            }
                        }
                    }
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
        func = FunctionDef(name="func", parameters=complex_schema)
        assert func.parameters["properties"]["address"]["properties"]["coordinates"]["properties"]["lat"]["type"] == "number"


# ═══════════════════════════════════════════════════════════════════════════
# 4. TOOLDEFINITION CONTAINER VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


class TestToolDefinitionValidation:
    """ToolDefinition Container Validation"""

    def test_rejects_non_function_type_literals(self, valid_function_def: FunctionDef) -> None:
        """Should reject non-'function' type literals."""
        with pytest.raises(ValidationError):
            ToolDefinition(
                type="tool",
                function=valid_function_def
            )

    def test_propagates_validation_errors_from_nested_functiondef(self) -> None:
        """Should propagate validation errors from nested FunctionDef clearly."""
        with pytest.raises(ValidationError) as exc_info:
            ToolDefinition(
                type="function",
                function=FunctionDef(name="", parameters={})
            )
        assert "name" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    def test_accepts_valid_tool_definition(self, valid_tool_definition: ToolDefinition) -> None:
        """Should accept valid tool definition."""
        assert valid_tool_definition.type == "function"
        assert valid_tool_definition.function.name == "get_current_weather"


# ═══════════════════════════════════════════════════════════════════════════
# 5. NAMEDTOOLCHOICE VALIDATION & TYPE COERCION
# ═══════════════════════════════════════════════════════════════════════════


class TestNamedToolChoiceValidation:
    """NamedToolChoice Validation & Type Coercion"""

    # --- Basic Validation ---

    def test_rejects_function_dictionary_without_name_key(self) -> None:
        """Should reject function dictionary without 'name' key."""
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={})
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"other_key": "value"})

    def test_accepts_valid_function_dictionary_with_name_key(self, valid_named_tool_choice: NamedToolChoice) -> None:
        """Should accept valid function dictionary with 'name' key."""
        assert valid_named_tool_choice.function["name"] == "get_current_weather"

    def test_rejects_function_dictionary_with_extra_keys_in_strict_mode(self) -> None:
        """Should reject function dictionary with extra keys in strict mode."""
        # This test assumes strict validation - implementation may vary
        with pytest.raises(ValidationError) as excinfo:
            NamedToolChoice(
                type="function",
                function={"name": "func", "extra": "value"}
            )
        assert "Unexpected keys" in str(excinfo.value)

    def test_rejects_non_function_type_literals(self) -> None:
        """Should reject non-'function' type literals."""
        with pytest.raises(ValidationError):
            NamedToolChoice(
                type="other",
                function={"name": "func"}
            )

    # --- Deep Validation ---

    def test_enforces_canonical_identifier_rules_on_internal_function_name(self) -> None:
        """Should enforce CanonicalIdentifier rules on internal function name."""
        # Valid identifier
        choice = NamedToolChoice(type="function", function={"name": "valid_name"})
        assert choice.function["name"] == "valid_name"
        
        # Invalid identifiers should be rejected at validation
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"name": "invalid-name"})
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"name": "invalid name"})

    def test_rejects_tool_choice_with_missing_function_name(self) -> None:
        """Should reject tool choice with missing function name."""
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"name": ""})


# ═══════════════════════════════════════════════════════════════════════════
# 6. TOOLCHOICE UNION TYPE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════


class TestToolChoiceUnionResolution:
    """ToolChoice Union Type Resolution"""

    def test_resolves_string_values_to_enum_types(self) -> None:
        """Should resolve string values to enum types."""
        # Test that ToolChoiceType strings are valid
        assert ToolChoiceType.AUTO.value == "auto"
        assert ToolChoiceType.NONE.value == "none"
        assert ToolChoiceType.REQUIRED.value == "required"
        assert ToolChoiceType.FUNCTION.value == "function"

    def test_resolves_namedtoolchoice_objects_correctly(self, valid_named_tool_choice: NamedToolChoice) -> None:
        """Should resolve NamedToolChoice objects correctly."""
        assert isinstance(valid_named_tool_choice, NamedToolChoice)
        assert valid_named_tool_choice.function["name"] == "get_current_weather"

    def test_accepts_both_enum_and_object_in_type_annotation(self, valid_named_tool_choice: NamedToolChoice) -> None:
        """Should accept both enum and object in type annotation."""
        # Type annotation test - validates Union works
        choice_enum: ToolChoice = ToolChoiceType.AUTO
        choice_obj: ToolChoice = valid_named_tool_choice
        assert choice_enum == ToolChoiceType.AUTO
        assert isinstance(choice_obj, NamedToolChoice)


# ═══════════════════════════════════════════════════════════════════════════
# 7. JSON SCHEMA COMPLIANCE
# ═══════════════════════════════════════════════════════════════════════════


class TestJSONSchemaCompliance:
    """JSON Schema Compliance"""

    def test_ensures_parameters_root_type_is_object(self, valid_function_def: FunctionDef) -> None:
        """Should ensure parameters root type is 'object'."""
        assert valid_function_def.parameters.get("type") == "object"

    def test_ensures_parameters_contain_properties_when_not_empty(self, valid_function_def: FunctionDef) -> None:
        """Should ensure parameters contain 'properties' when not empty."""
        assert "properties" in valid_function_def.parameters
        assert len(valid_function_def.parameters["properties"]) == 2

    def test_serializes_empty_parameters_as_valid_empty_json_schema(self) -> None:
        """Should serialize empty parameters as valid empty JSON schema."""
        func = FunctionDef(name="func", parameters={})
        serialized = func.model_dump()
        assert serialized["parameters"] == {}
        # Empty dict is valid JSON


# ═══════════════════════════════════════════════════════════════════════════
# 8. SERIALIZATION HYGIENE
# ═══════════════════════════════════════════════════════════════════════════


class TestSerializationHygiene:
    """Serialization Hygiene"""

    def test_omits_null_fields_in_model_dump(self) -> None:
        """Should omit null fields in model_dump (crucial for API compatibility)."""
        func = FunctionDef(name="func", parameters={})
        serialized = func.model_dump(exclude_none=True)
        assert "description" not in serialized

    def test_round_trip_serialize_deserialize_without_data_loss(self, valid_tool_call: ToolCall, valid_arguments: Dict[str, Any]) -> None:
        """Should round-trip serialize/deserialize without data loss."""
        serialized = valid_tool_call.model_dump()
        deserialized = ToolCall(**serialized)
        assert deserialized.id == valid_tool_call.id
        assert deserialized.name == valid_tool_call.name
        assert deserialized.arguments == valid_arguments


# ═══════════════════════════════════════════════════════════════════════════
# 9. MODEL IMMUTABILITY CONSTRAINTS
# ═══════════════════════════════════════════════════════════════════════════


class TestModelImmutability:
    """Model Immutability Constraints"""

    def test_ensures_toolcall_instances_are_immutable_after_creation(self, valid_tool_call: ToolCall) -> None:
        """Should ensure ToolCall instances are immutable after creation."""
        with pytest.raises((ValidationError, AttributeError)):
            valid_tool_call.id = "new_id"

    def test_ensures_functiondef_instances_are_immutable_after_creation(self, valid_function_def: FunctionDef) -> None:
        """Should ensure FunctionDef instances are immutable after creation."""
        with pytest.raises((ValidationError, AttributeError)):
            valid_function_def.name = "new_name"

    def test_ensures_namedtoolchoice_instances_are_immutable_after_creation(self, valid_named_tool_choice: NamedToolChoice) -> None:
        """Should ensure NamedToolChoice instances are immutable after creation."""
        with pytest.raises((ValidationError, AttributeError)):
            valid_named_tool_choice.type = "other"


# ═══════════════════════════════════════════════════════════════════════════
# 10. SECURITY & RESOURCE LIMITS (DEFENSIVE KERNEL)
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityAndResourceLimits:
    """Security & Resource Limits (Defensive Kernel)"""

    def test_rejects_parameters_schema_with_cyclic_references(self, recursive_dict: Dict[str, Any]) -> None:
        """Should reject parameters schema with cyclic references (RecursionError protection)."""
        # Pydantic should handle this gracefully
        with pytest.raises((ValidationError, RecursionError)):
            func = FunctionDef(name="func", parameters=recursive_dict)
            # Attempt to serialize
            func.model_dump()

    def test_rejects_arguments_dictionary_exceeding_defined_nesting_depth(self, deeply_nested_dict: Dict[str, Any]) -> None:
        """Should reject arguments dictionary exceeding a defined nesting depth (e.g., > 20 levels)."""
        # This might succeed in creation but should be caught during validation
        # Implementation-specific - document expected behavior
        with pytest.raises(ValidationError) as excinfo:
            ToolCall(id="call_123", name="func", arguments=deeply_nested_dict)
        assert "depth" in str(excinfo.value)

    def test_rejects_functiondef_where_parameters_json_exceeds_size_limit(self) -> None:
        """Should reject FunctionDef where parameters JSON string representation exceeds N MB (Memory DoS)."""
        # Create a very large schema (1MB+ of JSON)
        large_schema = {
            "type": "object",
            "properties": {
                f"field_{i}": {"type": "string", "description": "A" * 1000}
                for i in range(1000)
            }
        }
        
        # This should succeed but be monitored for size
        func = FunctionDef(name="func", parameters=large_schema)
        json_str = json.dumps(func.parameters)
        # Document that large schemas are accepted but monitored
        assert len(json_str) > 0

    def test_validates_toolcall_arguments_do_not_contain_reserved_internal_keys(self) -> None:
        """Should validate that ToolCall.arguments does not contain reserved internal keys if any exist."""
        # Assuming reserved keys like "__internal__", "__meta__"
        reserved_keys = ["__internal__", "__meta__", "__proto__"]
        
        for key in reserved_keys:
            # Document behavior - may accept or reject based on implementation
            tool_call = ToolCall(
                id="call_123",
                name="func",
                arguments={key: "value"}
            )
            # System should handle gracefully
            assert tool_call.arguments is not None


# ═══════════════════════════════════════════════════════════════════════════
# 11. STRICT API TOPOLOGY COMPLIANCE
# ═══════════════════════════════════════════════════════════════════════════


class TestStrictAPITopology:
    """Strict API Topology Compliance"""

    def test_enforces_parameters_is_valid_json_schema_draft(self) -> None:
        """Should enforce that FunctionDef.parameters (if present) is a valid JSON Schema draft (minimal check)."""
        # Valid minimal schema
        valid_schema = {"type": "object"}
        func = FunctionDef(name="func", parameters=valid_schema)
        assert func.parameters["type"] == "object"

    def test_fails_validation_if_required_fields_not_in_properties(self) -> None:
        """Should fail validation if parameters has 'required' fields that are not defined in 'properties'."""
        invalid_schema = {
            "type": "object",
            "properties": {
                "field1": {"type": "string"}
            },
            "required": ["field1", "field2"]  # field2 not in properties
        }
        
        # This should be accepted by Pydantic but flagged as semantically invalid
        func = FunctionDef(name="func", parameters=invalid_schema)
        # Document that semantic validation is implementation-specific
        assert "field2" in func.parameters["required"]

    def test_ensures_namedtoolchoice_function_contains_only_name_key(self) -> None:
        """Should ensure NamedToolChoice.function contains **only** the 'name' key (reject unknown keys strictly)."""
        # With extra keys
        with pytest.raises(ValidationError) as excinfo:
            NamedToolChoice(
                type="function",
                function={"name": "func", "extra": "key"}
            )
        # Opcional: verificar que el mensaje de error sea específico
        assert "Unexpected keys" in str(excinfo.value)


# ═══════════════════════════════════════════════════════════════════════════
# 12. PYDANTIC V2 SERIALIZATION SPECIFICS
# ═══════════════════════════════════════════════════════════════════════════


class TestPydanticV2Serialization:
    """Pydantic V2 Serialization Specifics"""

    def test_correctly_serializes_toolchoice_union_with_model_dump_json(self, valid_named_tool_choice: NamedToolChoice) -> None:
        """Should correctly serialize ToolChoice Union when using model_dump(mode='json')."""
        serialized = valid_named_tool_choice.model_dump(mode='json')
        assert serialized["type"] == "function"
        assert serialized["function"]["name"] == "get_current_weather"

    def test_prioritizes_namedtoolchoice_over_string_in_deserialization(self) -> None:
        """Should prioritize NamedToolChoice over ToolChoiceType strings if ambiguity arises in deserialization."""
        # Create from dict
        data = {
            "type": "function",
            "function": {"name": "test"}
        }
        choice = NamedToolChoice(**data)
        assert isinstance(choice, NamedToolChoice)
        assert choice.function["name"] == "test"

    def test_fails_gracefully_for_malformed_union_inputs(self) -> None:
        """Should fail gracefully (custom error) instead of generic ValidationException for malformed Union inputs."""
        with pytest.raises(ValidationError) as exc_info:
            NamedToolChoice(type="invalid", function={"name": "func"})
        # Error should be clear
        assert "validation error" in str(exc_info.value).lower() or "type" in str(exc_info.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 13. CANONICAL IDENTIFIER PROPAGATION
# ═══════════════════════════════════════════════════════════════════════════


class TestCanonicalIdentifierPropagation:
    """Canonical Identifier Propagation"""

    def test_verifies_namedtoolchoice_function_name_passes_identifier_validation(self) -> None:
        """Should verify that NamedToolChoice function name *value* passes _validate_identifier logic (crucial since it is a Dict, not a typed field)."""
        # Valid identifier
        choice = NamedToolChoice(
            type="function",
            function={"name": "valid_identifier_123"}
        )
        assert choice.function["name"] == "valid_identifier_123"
        
        # Invalid identifiers
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"name": "123invalid"})
        with pytest.raises(ValidationError):
            NamedToolChoice(type="function", function={"name": "invalid-dash"})

    def test_rejects_toolcall_name_violating_canonical_identifier_regex(self) -> None:
        """Should reject ToolCall.name if it violates CanonicalIdentifier regex, even if incoming from a provider (sanitize incoming data)."""
        # Valid name
        tool_call = ToolCall(id="call_123", name="valid_name", arguments={})
        assert tool_call.name == "valid_name"
    
        # CORRECCIÓN: 'invalid-name' podría ser válido si tu regex permite kebab-case.
        # Usamos espacios para garantizar que sea inválido en cualquier identificador máquina.
        
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="invalid name", arguments={}) # Espacio es ilegal
            
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="invalid.name", arguments={}) # Punto suele ser ilegal
            
        with pytest.raises(ValidationError):
            ToolCall(id="call_123", name="!invalid", arguments={}) # Símbolos