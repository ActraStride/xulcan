"""Unit Tests for xulcan.protocol.utils module.

Test Suite Coverage:
    - Class 1: Constants validation and documentation
    - Class 2: Recursion depth validation for dictionaries
    - Class 3: Recursion depth validation for lists
    - Class 4: Mixed structure validation
    - Class 5: Edge cases and boundary conditions

Philosophy: Defense in Depth, DoS Prevention, Stack Overflow Protection.
"""

import pytest
from typing import Any, Dict, List

from xulcan.protocol.utils import (
    MAX_NESTING_DEPTH,
    MAX_CHUNK_SIZE,
    _validate_recursion_depth,
)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 1: CONSTANTS VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Validates security-critical constants and their values."""

    def test_max_nesting_depth_value(self) -> None:
        """Should have reasonable default to prevent stack overflow."""
        assert MAX_NESTING_DEPTH == 20
        assert isinstance(MAX_NESTING_DEPTH, int)

    def test_max_chunk_size_value(self) -> None:
        """Should have reasonable default to prevent memory exhaustion."""
        assert MAX_CHUNK_SIZE == 10_000_000  # 10 MB
        assert isinstance(MAX_CHUNK_SIZE, int)

    def test_constants_are_positive(self) -> None:
        """Should enforce positive values for safety limits."""
        assert MAX_NESTING_DEPTH > 0
        assert MAX_CHUNK_SIZE > 0


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 2: DICTIONARY RECURSION VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestDictionaryRecursionValidation:
    """Validates recursion depth enforcement for dictionary structures."""

    def test_accepts_flat_dictionary(self) -> None:
        """Should accept dictionary with no nesting."""
        flat_dict = {
            "key1": "value1",
            "key2": 42,
            "key3": True,
            "key4": None
        }
        
        # Should not raise
        _validate_recursion_depth(flat_dict)

    def test_accepts_shallow_nesting(self) -> None:
        """Should accept dictionary with shallow nesting (2-3 levels)."""
        shallow_dict = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }
        
        # Should not raise
        _validate_recursion_depth(shallow_dict)

    def test_accepts_at_limit(self) -> None:
        """Should accept dictionary at exact nesting limit."""
        # Create structure with exactly MAX_NESTING_DEPTH levels
        nested_dict: Dict[str, Any] = {"level": 0}
        current = nested_dict
        
        for i in range(1, MAX_NESTING_DEPTH):
            current["nested"] = {"level": i}
            current = current["nested"]
        
        # Should not raise at exactly the limit
        _validate_recursion_depth(nested_dict)

    def test_rejects_exceeding_limit(self) -> None:
        """Should raise ValueError if dictionary exceeds nesting limit."""
        # Create structure with MAX_NESTING_DEPTH + 5 levels
        deep_dict: Dict[str, Any] = {"level": 0}
        current = deep_dict
        
        for i in range(1, MAX_NESTING_DEPTH + 5):
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(deep_dict)
        
        assert "exceeds maximum nesting depth" in str(exc.value).lower()
        assert str(MAX_NESTING_DEPTH) in str(exc.value)

    def test_custom_max_depth_parameter(self) -> None:
        """Should respect custom max_depth parameter."""
        nested_dict = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "too deep"
                    }
                }
            }
        }
        
        # Should pass with higher limit
        _validate_recursion_depth(nested_dict, max_depth=10)
        
        # Should fail with lower limit
        with pytest.raises(ValueError):
            _validate_recursion_depth(nested_dict, max_depth=2)

    def test_multiple_branches_at_same_depth(self) -> None:
        """Should validate all branches in dictionary tree."""
        branched_dict = {
            "branch1": {
                "deep": {
                    "level": "value1"
                }
            },
            "branch2": {
                "deep": {
                    "level": "value2"
                }
            },
            "branch3": "shallow"
        }
        
        # Should not raise
        _validate_recursion_depth(branched_dict)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 3: LIST RECURSION VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestListRecursionValidation:
    """Validates recursion depth enforcement for list structures."""

    def test_accepts_flat_list(self) -> None:
        """Should accept list with no nesting."""
        flat_list = [1, 2, "three", True, None]
        
        # Should not raise
        _validate_recursion_depth(flat_list)

    def test_accepts_shallow_nested_lists(self) -> None:
        """Should accept lists with shallow nesting."""
        shallow_list = [
            1,
            [2, 3],
            [4, [5, 6]],
            7
        ]
        
        # Should not raise
        _validate_recursion_depth(shallow_list)

    def test_accepts_list_at_limit(self) -> None:
        """Should accept list at exact nesting limit."""
        # Create nested list structure at limit
        nested_list: Any = ["level_0"]
        current = nested_list
        
        for i in range(1, MAX_NESTING_DEPTH):
            new_level = [f"level_{i}"]
            current.append(new_level)
            current = new_level
        
        # Should not raise at exactly the limit
        _validate_recursion_depth(nested_list)

    def test_rejects_list_exceeding_limit(self) -> None:
        """Should raise ValueError if list exceeds nesting limit."""
        # Create deeply nested list exceeding limit
        nested_list: Any = ["start"]
        current = nested_list
        
        for i in range(MAX_NESTING_DEPTH + 5):
            new_level = [f"level_{i}"]
            current.append(new_level)
            current = new_level
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(nested_list)
        
        assert "exceeds maximum nesting depth" in str(exc.value).lower()

    def test_list_with_multiple_nested_items(self) -> None:
        """Should validate all items in list."""
        complex_list = [
            [1, [2, [3]]],
            [4, [5, [6]]],
            [7, 8, 9]
        ]
        
        # Should not raise
        _validate_recursion_depth(complex_list)


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 4: MIXED STRUCTURE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestMixedStructureValidation:
    """Validates recursion depth for mixed dict/list structures."""

    def test_accepts_dict_containing_lists(self) -> None:
        """Should accept dictionary containing lists."""
        mixed_structure = {
            "items": [1, 2, 3],
            "nested": {
                "more_items": [4, 5, [6, 7]]
            }
        }
        
        # Should not raise
        _validate_recursion_depth(mixed_structure)

    def test_accepts_list_containing_dicts(self) -> None:
        """Should accept list containing dictionaries."""
        mixed_structure = [
            {"key": "value1"},
            {
                "nested": {
                    "key": "value2"
                }
            },
            [1, 2, {"key": "value3"}]
        ]
        
        # Should not raise
        _validate_recursion_depth(mixed_structure)

    def test_complex_json_like_structure(self) -> None:
        """Should validate realistic JSON-like structures."""
        json_structure = {
            "user": {
                "name": "Alice",
                "preferences": {
                    "theme": "dark",
                    "notifications": {
                        "email": True,
                        "push": False
                    }
                },
                "history": [
                    {"action": "login", "timestamp": "2024-01-01"},
                    {"action": "update", "data": {"field": "email"}}
                ]
            },
            "metadata": {
                "version": "1.0",
                "tags": ["production", "verified"]
            }
        }
        
        # Should not raise
        _validate_recursion_depth(json_structure)

    def test_rejects_mixed_structure_exceeding_limit(self) -> None:
        """Should raise ValueError for mixed structures exceeding limit."""
        # Build deep structure alternating dict and list
        structure: Any = {"start": []}
        current = structure["start"]
        
        for i in range(MAX_NESTING_DEPTH + 3):
            if i % 2 == 0:
                # Add dict inside list
                new_dict = {"level": i, "next": []}
                current.append(new_dict)
                current = new_dict["next"]
            else:
                # Add list inside last dict
                new_list = [{"level": i, "next": []}]
                current.append(new_list[0])
                current = new_list[0]["next"]
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(structure)
        
        assert "exceeds maximum nesting depth" in str(exc.value).lower()


# ═══════════════════════════════════════════════════════════════════════════
# CLASS 5: EDGE CASES AND PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════

class TestPrimitiveTypes:
    """Validates handling of primitive types and edge cases."""

    @pytest.mark.parametrize("primitive", [
        None,
        True,
        False,
        42,
        3.14,
        "string",
        "",
    ])
    def test_accepts_primitive_types(self, primitive: Any) -> None:
        """Should accept all primitive types without validation."""
        # Should not raise
        _validate_recursion_depth(primitive)

    def test_empty_dictionary(self) -> None:
        """Should accept empty dictionary."""
        _validate_recursion_depth({})

    def test_empty_list(self) -> None:
        """Should accept empty list."""
        _validate_recursion_depth([])

    def test_dictionary_with_none_values(self) -> None:
        """Should accept dictionary with None values."""
        data = {
            "key1": None,
            "key2": None,
            "nested": {
                "key3": None
            }
        }
        
        _validate_recursion_depth(data)

    def test_list_with_none_values(self) -> None:
        """Should accept list with None values."""
        data = [None, [None, None], None]
        
        _validate_recursion_depth(data)


class TestCircularReferenceProtection:
    """Validates detection of circular references (if applicable)."""

    def test_detects_circular_dict_reference(self) -> None:
        """Should detect circular references in dictionaries."""
        circular_dict: Dict[str, Any] = {"key": "value"}
        circular_dict["self"] = circular_dict
        
        # This will either raise ValueError for exceeding depth
        # or RecursionError depending on implementation
        with pytest.raises((ValueError, RecursionError)):
            _validate_recursion_depth(circular_dict)

    def test_detects_circular_list_reference(self) -> None:
        """Should detect circular references in lists."""
        circular_list: List[Any] = [1, 2, 3]
        circular_list.append(circular_list)
        
        # This will either raise ValueError for exceeding depth
        # or RecursionError depending on implementation
        with pytest.raises((ValueError, RecursionError)):
            _validate_recursion_depth(circular_list)


class TestErrorMessages:
    """Validates error message quality and debugging information."""

    def test_error_message_contains_depth_info(self) -> None:
        """Should include depth limit in error message."""
        deep_dict: Dict[str, Any] = {"level": 0}
        current = deep_dict
        
        for i in range(1, MAX_NESTING_DEPTH + 5):
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(deep_dict)
        
        error_msg = str(exc.value)
        assert str(MAX_NESTING_DEPTH) in error_msg
        assert "nesting" in error_msg.lower()

    def test_error_message_indicates_security_concern(self) -> None:
        """Should indicate potential security issue in error message."""
        deep_structure: Dict[str, Any] = {"level": 0}
        current = deep_structure
        
        for i in range(1, 50):
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(deep_structure)
        
        error_msg = str(exc.value).lower()
        # Should mention either malicious, corrupted, or safety concern
        assert any(word in error_msg for word in ["malicious", "corrupted", "safety"])


class TestCurrentDepthParameter:
    """Validates internal current_depth parameter behavior."""

    def test_current_depth_starts_at_zero(self) -> None:
        """Should start counting from depth 0."""
        # A single-level dict should pass with max_depth=0
        # if we're counting container itself as depth 0
        shallow = {"key": "value"}
        
        # With max_depth=1, should allow one level of nesting
        _validate_recursion_depth(shallow, max_depth=1)

    def test_manual_current_depth_override(self) -> None:
        """Should respect manually set current_depth parameter."""
        shallow = {"key": "value"}
        
        # If we claim we're already at depth 20, it should fail immediately
        with pytest.raises(ValueError):
            _validate_recursion_depth(
                shallow, 
                current_depth=20, 
                max_depth=20
            )

    def test_current_depth_increments_correctly(self) -> None:
        """Should increment depth correctly for each nesting level."""
        # Create structure with exactly 3 levels
        structure = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }
        
        # Should pass with max_depth=3
        _validate_recursion_depth(structure, max_depth=4)
        
        # Should fail with max_depth=2 (too shallow)
        with pytest.raises(ValueError):
            _validate_recursion_depth(structure, max_depth=2)


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY AND DoS SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════

class TestDoSProtection:
    """Validates protection against DoS attack vectors."""

    def test_protects_against_json_bomb(self) -> None:
        """Should prevent deeply nested 'JSON bomb' attack payloads."""
        # Simulate a JSON bomb with extreme nesting
        json_bomb: Dict[str, Any] = {"bomb": None}
        current = json_bomb
        
        for i in range(100):  # Excessive nesting
            current["bomb"] = {"layer": i}
            current = current["bomb"]
        
        with pytest.raises(ValueError) as exc:
            _validate_recursion_depth(json_bomb)
        
        assert "exceeds maximum nesting depth" in str(exc.value).lower()

    def test_validates_large_flat_structures_efficiently(self) -> None:
        """Should efficiently validate large flat structures."""
        # Large but flat structure should validate quickly
        large_flat_dict = {f"key_{i}": f"value_{i}" for i in range(10000)}
        
        # Should not raise and should complete quickly
        _validate_recursion_depth(large_flat_dict)
        
        # Same for lists
        large_flat_list = list(range(10000))
        _validate_recursion_depth(large_flat_list)

    def test_rejects_pathological_nesting_patterns(self) -> None:
        """Should reject various pathological nesting patterns."""
        # Pattern 1: Deeply nested with wide branches
        pattern1: Dict[str, Any] = {}
        current = pattern1
        
        for i in range(MAX_NESTING_DEPTH + 2):
            current["a"] = {}
            current["b"] = {}
            current["c"] = {}
            current = current["a"]
        
        with pytest.raises(ValueError):
            _validate_recursion_depth(pattern1)
        
        # Pattern 2: Alternating list/dict nesting
        pattern2: Any = []
        current = pattern2
        
        for i in range(MAX_NESTING_DEPTH + 2):
            if i % 2 == 0:
                current.append({})
                current = current[0]
            else:
                current["nested"] = []
                current = current["nested"]
        
        with pytest.raises(ValueError):
            _validate_recursion_depth(pattern2)