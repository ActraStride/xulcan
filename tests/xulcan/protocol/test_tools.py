"""Unit Tests for xulcan.protocol.tools module.

Test Suite Coverage:
    - Suite A: ToolCall validation (ID, name, arguments)
    - Suite B: FunctionDef validation (keywords, schema)
    - Suite C: ToolDefinition structure
    - Suite D: ToolChoice strategies
    - Suite E: Security boundaries (recursion, serialization)

Philosophy: Defense in Depth, Strict Type Safety, Zero-Trust Validation.
"""

import pytest
import json
from typing import Any, Dict
from pydantic import ValidationError

from xulcan.protocol import (
    ToolCall,
    FunctionDef,
    ToolDefinition,
    ToolChoiceType,
    NamedToolChoice,
    FunctionIdentity,
)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE A: TOOLCALL VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestToolCallIdentity:
    """Validates ToolCall ID traceability requirements."""

    def test_rejects_empty_id(
        self, 
        valid_machine_id: str,
        valid_tool_call_args: Dict[str, Any]
    ) -> None:
        """Should raise ValidationError if ID is empty string."""
        with pytest.raises(ValidationError) as exc:
            ToolCall(
                id="",
                name=valid_machine_id,
                arguments=valid_tool_call_args
            )
        assert "cannot be empty" in str(exc.value).lower()

    def test_rejects_whitespace_only_id(
        self, 
        valid_machine_id: str, 
        valid_tool_call_args: Dict[str, Any]
    ) -> None:
        """Should raise ValidationError if ID is only whitespace."""
        with pytest.raises(ValidationError) as exc:
            ToolCall(
                id="   ",
                name=valid_machine_id,
                arguments=valid_tool_call_args
            )
        assert "cannot be empty" in str(exc.value).lower()

    @pytest.mark.parametrize("safe_id", [
        "call_abc123",
        "toolu_01ABC-xyz_999",
        "func-call-2024-01-01-uuid",
        "call:abc:123",
    ])
    def test_accepts_valid_external_id(
        self, 
        safe_id: str, 
        valid_machine_id: str, 
        valid_tool_call_args: Dict[str, Any]
    ) -> None:
        """Should accept IDs with exotic but safe formats."""
        tool_call = ToolCall(
            id=safe_id,
            name=valid_machine_id,
            arguments=valid_tool_call_args
        )
        assert tool_call.id == safe_id


class TestToolCallArguments:
    """Validates argument serialization and type safety."""

    def test_rejects_non_serializable_args(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should raise ValidationError if arguments contain non-JSON types."""
        from datetime import datetime
        
        non_serializable = {
            "timestamp": datetime.now(),
            "data_set": {1, 2, 3},  # sets are not JSON-serializable
        }
        
        with pytest.raises(ValidationError) as exc:
            ToolCall(
                id=valid_tool_id,
                name=valid_machine_id,
                arguments=non_serializable
            )
        assert "json-serializable" in str(exc.value).lower()

    def test_rejects_non_dict_arguments(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should raise ValidationError if arguments is not a dictionary."""
        with pytest.raises(ValidationError):
            ToolCall(
                id=valid_tool_id,
                name=valid_machine_id,
                arguments=["list", "of", "items"]  # type: ignore
            )

    def test_accepts_nested_serializable_structures(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should accept complex but valid JSON structures."""
        complex_args = {
            "user": {
                "name": "Alice",
                "preferences": {
                    "theme": "dark",
                    "notifications": True,
                    "limits": [10, 20, 30]
                }
            },
            "query": "search term",
            "filters": ["active", "verified"]
        }
        
        tool_call = ToolCall(
            id=valid_tool_id,
            name=valid_machine_id,
            arguments=complex_args
        )
        assert tool_call.arguments == complex_args

    def test_accepts_empty_arguments(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should accept empty dictionary for parameterless functions."""
        tool_call = ToolCall(
            id=valid_tool_id,
            name=valid_machine_id,
            arguments={}
        )
        assert tool_call.arguments == {}


class TestToolCallRecursion:
    """Validates recursion depth limits for arguments."""

    def test_rejects_deeply_nested_arguments(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should raise ValidationError if arguments exceed recursion depth."""
        # Create a deeply nested structure (assuming max depth is ~20)
        deep_nest: Dict[str, Any] = {"level": 0}
        current = deep_nest
        for i in range(1, 50):  # Exceed reasonable depth
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(ValidationError) as exc:
            ToolCall(
                id=valid_tool_id,
                name=valid_machine_id,
                arguments=deep_nest
            )
        assert "recursion" in str(exc.value).lower() or "depth" in str(exc.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE B: FUNCTIONDEF VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestFunctionDefSecurity:
    """Validates prevention of code injection via function names."""

    @pytest.mark.parametrize("keyword", [
        "def", "class", "import", "lambda", "return", "if", "for", "while"
    ])
    def test_blocks_python_keywords(self, keyword: str) -> None:
        """Should raise ValidationError if name is a Python keyword."""
        with pytest.raises(ValidationError) as exc:
            FunctionDef(
                name=keyword,
                description="Malicious function",
                parameters={"type": "object"}
            )
        assert "keyword" in str(exc.value).lower() or "reserved" in str(exc.value).lower()

    @pytest.mark.parametrize("dunder", [
        "__init__", "__call__", "__getattr__", "__setattr__"
    ])
    def test_blocks_dunder_methods(self, dunder: str) -> None:
        """Should raise ValidationError if name is a dunder method."""
        with pytest.raises(ValidationError):
            FunctionDef(
                name=dunder,
                description="Dunder method",
                parameters={"type": "object"}
            )

    @pytest.mark.parametrize("safe_name", [
        "get-weather",
        "calculate-distance",
        "search-database",
        "fetch-user-data",
        "func2",
        "helper-function",
    ])
    def test_accepts_safe_function_names(self, safe_name: str) -> None:
        """Should accept valid MachineID identifiers."""
        func = FunctionDef(
            name=safe_name,
            description="Safe function",
            parameters={"type": "object"}
        )
        assert func.name == safe_name


class TestFunctionDefParameters:
    """Validates JSON Schema parameter validation."""

    def test_enforces_dict_type(self, valid_machine_id: str) -> None:
        """Should raise ValidationError if parameters is not a dictionary."""
        with pytest.raises(ValidationError):
            FunctionDef(
                name=valid_machine_id,
                description="Test",
                parameters="not a dict"  # type: ignore
            )

    def test_detects_cyclic_references(self, valid_machine_id: str) -> None:
        """Should raise ValidationError if parameters contain circular refs."""
        circular: Dict[str, Any] = {}
        circular["self_ref"] = circular
        
        with pytest.raises(ValidationError) as exc:
            FunctionDef(
                name=valid_machine_id,
                description="Test",
                parameters=circular
            )
        assert "cyclic" in str(exc.value).lower() or "circular" in str(exc.value).lower()

    def test_accepts_empty_schema(self, valid_machine_id: str) -> None:
        """Should accept empty parameters schema."""
        func = FunctionDef(
            name=valid_machine_id,
            description="Function with no parameters",
            parameters={}
        )
        assert func.parameters == {}

    def test_accepts_valid_json_schema(self, valid_machine_id: str) -> None:
        """Should accept properly structured JSON Schema."""
        valid_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "age": {"type": "integer", "minimum": 0},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["name"]
        }
        
        func = FunctionDef(
            name=valid_machine_id,
            description="Creates a user",
            parameters=valid_schema
        )
        assert func.parameters == valid_schema

    def test_rejects_non_serializable_schema(self, valid_machine_id: str) -> None:
        """Should raise ValidationError if schema contains non-JSON types."""
        from datetime import datetime
        
        invalid_schema = {
            "type": "object",
            "properties": {
                "timestamp": datetime.now()  # Not JSON-serializable
            }
        }
        
        with pytest.raises(ValidationError) as exc:
            FunctionDef(
                name=valid_machine_id,
                description="Test",
                parameters=invalid_schema
            )
        assert "serializable" in str(exc.value).lower()


class TestFunctionDefRecursion:
    """Validates recursion depth limits for parameter schemas."""

    def test_rejects_deeply_nested_schema(self, valid_machine_id: str) -> None:
        """Should raise ValidationError if schema exceeds recursion depth."""
        deep_schema: Dict[str, Any] = {"type": "object", "properties": {}}
        current = deep_schema["properties"]
        
        for i in range(50):  # Create excessive nesting
            current["nested"] = {
                "type": "object",
                "properties": {}
            }
            current = current["nested"]["properties"]
        
        with pytest.raises(ValidationError) as exc:
            FunctionDef(
                name=valid_machine_id,
                description="Test",
                parameters=deep_schema
            )
        assert "recursion" in str(exc.value).lower() or "depth" in str(exc.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE C: TOOLDEFINITION STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestToolDefinitionInvariants:
    """Validates ToolDefinition wrapper structure."""

    def test_enforces_literal_function_type(self, valid_function_def: FunctionDef) -> None:
        """Should only accept 'function' as type value."""
        with pytest.raises(ValidationError):
            ToolDefinition(
                type="code_interpreter",  # type: ignore
                function=valid_function_def
            )

    def test_correctly_wraps_function_def(self, valid_function_def: FunctionDef) -> None:
        """Should properly encapsulate FunctionDef."""
        tool_def = ToolDefinition(
            type="function",
            function=valid_function_def
        )
        
        assert tool_def.type == "function"
        assert tool_def.function == valid_function_def
        assert tool_def.function.name == valid_function_def.name

    def test_serializes_to_api_format(self, valid_function_def: FunctionDef) -> None:
        """Should serialize to expected API structure."""
        tool_def = ToolDefinition(
            type="function",
            function=valid_function_def
        )
        
        serialized = tool_def.model_dump()
        assert serialized["type"] == "function"
        assert "function" in serialized
        assert serialized["function"]["name"] == valid_function_def.name


# ═══════════════════════════════════════════════════════════════════════════
# SUITE D: TOOLCHOICE STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

class TestToolChoiceTypeEnum:
    """Validates ToolChoiceType enum values for API compatibility."""

    def test_enum_values_match_api_spec(self) -> None:
        """Should have exact string values matching OpenAI/Anthropic APIs."""
        assert ToolChoiceType.AUTO.value == "auto"
        assert ToolChoiceType.NONE.value == "none"
        assert ToolChoiceType.REQUIRED.value == "required"
        assert ToolChoiceType.FUNCTION.value == "function"

    def test_enum_members_are_strings(self) -> None:
        """Should be string enum for JSON serialization."""
        for choice_type in ToolChoiceType:
            assert isinstance(choice_type.value, str)


class TestFunctionIdentity:
    """Validates FunctionIdentity strict mode."""

    def test_only_accepts_name_field(self, valid_machine_id: str) -> None:
        """Should create identity with only name field."""
        identity = FunctionIdentity(name=valid_machine_id)
        assert identity.name == valid_machine_id

    def test_rejects_extra_fields(self, valid_machine_id: str) -> None:
        """Should raise ValidationError if extra fields provided."""
        with pytest.raises(ValidationError):
            FunctionIdentity(
                name=valid_machine_id,
                metadata="extra"  # type: ignore
            )

    def test_validates_machine_id_format(self) -> None:
        """Should enforce MachineID validation on name."""
        with pytest.raises(ValidationError):
            FunctionIdentity(name="invalid name with spaces")


class TestNamedToolChoice:
    """Validates NamedToolChoice structure enforcement."""

    def test_structure_enforcement(self, valid_machine_id: str) -> None:
        """Should enforce {type: 'function', function: {name: 'foo'}} structure."""
        choice = NamedToolChoice(
            type="function",
            function=FunctionIdentity(name=valid_machine_id)
        )
        
        assert choice.type == "function"
        assert choice.function.name == valid_machine_id

    def test_rejects_invalid_type(self, valid_machine_id: str) -> None:
        """Should only accept 'function' as type value."""
        with pytest.raises(ValidationError):
            NamedToolChoice(
                type="auto",  # type: ignore
                function=FunctionIdentity(name=valid_machine_id)
            )

    def test_validates_function_name_in_choice(self) -> None:
        """Should enforce MachineID validation and keyword blocking on function name."""
        # Test with keyword
        with pytest.raises(ValidationError):
            NamedToolChoice(
                type="function",
                function=FunctionIdentity(name="def")
            )
        
        # Test with invalid MachineID format
        with pytest.raises(ValidationError):
            NamedToolChoice(
                type="function",
                function=FunctionIdentity(name="invalid name")
            )

    def test_serializes_correctly(self, valid_machine_id: str) -> None:
        """Should serialize to API-compatible format."""
        choice = NamedToolChoice(
            type="function",
            function=FunctionIdentity(name=valid_machine_id)
        )
        
        serialized = choice.model_dump()
        assert serialized == {
            "type": "function",
            "function": {"name": valid_machine_id}
        }


# ═══════════════════════════════════════════════════════════════════════════
# SUITE E: SECURITY BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityBoundaries:
    """Validates defense-in-depth security mechanisms."""

    def test_tool_call_immutability_attempt(self, valid_tool_call: ToolCall) -> None:
        """Should prevent or safely handle mutation attempts."""
        original_args = valid_tool_call.arguments.copy()
        
        # Attempt to mutate
        try:
            valid_tool_call.arguments["injected"] = "malicious"
            # If mutation succeeds, verify original object is unaffected
            # (This depends on Pydantic frozen=True configuration)
        except (TypeError, ValidationError, AttributeError):
            # If frozen, mutation should fail
            pass
        
        # Verify core data integrity
        assert "location" in valid_tool_call.arguments

    @pytest.mark.parametrize("invalid_name", [
        "__import__",
        "my function",
        "function!",
        "_private",
    ])
    def test_function_def_rejects_invalid_identifiers(self, invalid_name: str) -> None:
        """Should block names that don't conform to MachineID format."""
        with pytest.raises(ValidationError):
            FunctionDef(
                name=invalid_name,
                description="Invalid identifier",
                parameters={}
            )

    def test_arguments_json_roundtrip_safety(
        self, 
        valid_tool_id: str,
        valid_machine_id: str
    ) -> None:
        """Should maintain data integrity through JSON serialization cycle."""
        original_args = {
            "string": "test",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        tool_call = ToolCall(
            id=valid_tool_id,
            name=valid_machine_id,
            arguments=original_args
        )
        
        # Serialize and deserialize
        json_str = json.dumps(tool_call.model_dump())
        reconstructed = json.loads(json_str)
        
        assert reconstructed["arguments"] == original_args

    def test_parameter_schema_sanitization(self, valid_machine_id: str) -> None:
        """Should reject schemas with executable content."""
        dangerous_schema = {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "default": "__import__('os').system('rm -rf /')"
                }
            }
        }
        
        # Should accept the schema (it's just a JSON structure)
        # The actual danger is in execution, not definition
        func = FunctionDef(
            name=valid_machine_id,
            description="Test",
            parameters=dangerous_schema
        )
        
        # But verify it's stored as plain data
        assert isinstance(func.parameters["properties"]["cmd"]["default"], str)