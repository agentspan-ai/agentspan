# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for schema_utils — JSON Schema generation from type hints and Pydantic models."""

from typing import Any, Dict, List, Optional, Union

import pytest

from conductor.ai.agents._internal.schema_utils import (
    _type_to_json_schema,
    schema_from_function,
    schema_from_pydantic,
)


class TestTypeToJsonSchema:
    """Test _type_to_json_schema() for various Python types."""

    def test_str(self):
        assert _type_to_json_schema(str) == {"type": "string"}

    def test_int(self):
        assert _type_to_json_schema(int) == {"type": "integer"}

    def test_float(self):
        assert _type_to_json_schema(float) == {"type": "number"}

    def test_bool(self):
        assert _type_to_json_schema(bool) == {"type": "boolean"}

    def test_list(self):
        # Bare list must include "items" for OpenAI API compliance (BUG-P0-01)
        assert _type_to_json_schema(list) == {"type": "array", "items": {}}

    def test_dict(self):
        # Bare dict must include "additionalProperties" for schema compliance
        assert _type_to_json_schema(dict) == {"type": "object", "additionalProperties": {}}

    def test_none_type(self):
        assert _type_to_json_schema(type(None)) == {"type": "null"}

    def test_any_returns_empty(self):
        assert _type_to_json_schema(Any) == {}

    def test_optional_str(self):
        result = _type_to_json_schema(Optional[str])
        assert result == {"type": "string"}

    def test_optional_int(self):
        result = _type_to_json_schema(Optional[int])
        assert result == {"type": "integer"}

    def test_union_multiple_types(self):
        result = _type_to_json_schema(Union[str, int])
        # Multiple non-None args: returns empty dict
        assert result == {}

    def test_union_with_none_is_optional(self):
        result = _type_to_json_schema(Union[str, None])
        assert result == {"type": "string"}

    def test_list_with_items(self):
        result = _type_to_json_schema(List[str])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_list_with_int_items(self):
        result = _type_to_json_schema(List[int])
        assert result == {"type": "array", "items": {"type": "integer"}}

    def test_dict_with_value_type(self):
        result = _type_to_json_schema(Dict[str, int])
        assert result == {"type": "object", "additionalProperties": {"type": "integer"}}

    def test_unknown_type_returns_empty(self):
        # A custom class that's not in the mapping
        class CustomType:
            pass

        assert _type_to_json_schema(CustomType) == {}


class TestSchemaFromFunction:
    """Test schema_from_function() for various function signatures."""

    def test_simple_function(self):
        def greet(name: str, age: int) -> str:
            return f"Hello {name}"

        result = schema_from_function(greet)
        assert "input" in result
        assert "output" in result
        assert result["input"]["properties"]["name"]["type"] == "string"
        assert result["input"]["properties"]["age"]["type"] == "integer"
        assert result["input"]["required"] == ["name", "age"]
        assert result["output"]["type"] == "string"

    def test_function_with_defaults(self):
        def func(x: str, y: int = 10) -> str:
            return x

        result = schema_from_function(func)
        assert result["input"]["required"] == ["x"]

    def test_function_with_optional(self):
        def func(x: str, y: Optional[int] = None) -> str:
            return x

        result = schema_from_function(func)
        assert result["input"]["required"] == ["x"]
        assert result["input"]["properties"]["y"]["type"] == "integer"

    def test_skips_self_and_context(self):
        def method(self, context, x: str) -> str:
            return x

        result = schema_from_function(method)
        assert "self" not in result["input"]["properties"]
        assert "context" not in result["input"]["properties"]
        assert "x" in result["input"]["properties"]

    def test_no_return_type(self):
        def func(x: str):
            return x

        result = schema_from_function(func)
        assert result["output"] == {}

    def test_get_type_hints_exception(self):
        """When get_type_hints fails, falls back gracefully."""

        def func(x: str) -> str:
            return x

        # Simulate a function where get_type_hints raises
        from unittest.mock import patch

        with patch(
            "conductor.ai.agents._internal.schema_utils.get_type_hints",
            side_effect=Exception("broken"),
        ):
            result = schema_from_function(func)
            # Should still produce a schema with empty types
            assert "input" in result
            assert "x" in result["input"]["properties"]


class TestSchemaFromPydantic:
    """Test schema_from_pydantic() for Pydantic models."""

    def test_pydantic_v2_model(self):
        """Test with a Pydantic v2 BaseModel."""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class MyModel(BaseModel):
            name: str
            age: int

        result = schema_from_pydantic(MyModel)
        assert "properties" in result
        assert "name" in result["properties"]
        assert "age" in result["properties"]

    def test_non_pydantic_raises(self):
        class NotAModel:
            pass

        with pytest.raises(TypeError, match="is not a Pydantic BaseModel"):
            schema_from_pydantic(NotAModel)

    def test_plain_dict_raises(self):
        with pytest.raises(TypeError):
            schema_from_pydantic(dict)


# ── P4-F: Schema edge cases ───────────────────────────────────────────


class TestTypeToJsonSchemaEdgeCases:
    """Edge case tests for _type_to_json_schema."""

    def test_union_str_int_returns_empty(self):
        """Non-Optional Union returns empty dict."""
        result = _type_to_json_schema(Union[str, int])
        assert result == {}

    def test_list_of_list_of_str(self):
        """Nested generics: List[List[str]]."""
        result = _type_to_json_schema(List[List[str]])
        assert result["type"] == "array"
        assert result["items"]["type"] == "array"
        assert result["items"]["items"]["type"] == "string"

    def test_dict_str_any(self):
        """Dict[str, Any] → object with empty additionalProperties."""
        result = _type_to_json_schema(Dict[str, Any])
        assert result["type"] == "object"
        # Any maps to {}
        assert result.get("additionalProperties") == {}

    def test_optional_list(self):
        """Optional[List[str]] → array with items."""
        result = _type_to_json_schema(Optional[List[str]])
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"

    def test_bytes_type_unknown(self):
        """bytes is not in the mapping, returns empty dict."""
        result = _type_to_json_schema(bytes)
        assert result == {}

    def test_object_type(self):
        """Plain object returns empty dict."""
        result = _type_to_json_schema(object)
        assert result == {}


class TestBareCollectionTypes:
    """Regression tests for BUG-P0-01: bare list/dict must produce valid schemas.

    OpenAI API requires "items" on array schemas. Without it, tool calls
    fail with 400: 'array schema missing items'.
    """

    def test_bare_list_has_items(self):
        """Bare `list` includes empty 'items' dict."""
        result = _type_to_json_schema(list)
        assert result == {"type": "array", "items": {}}

    def test_bare_dict_has_additional_properties(self):
        """Bare `dict` includes empty 'additionalProperties' dict."""
        result = _type_to_json_schema(dict)
        assert result == {"type": "object", "additionalProperties": {}}

    def test_parameterized_list_still_works(self):
        """List[str] still generates correct typed items."""
        result = _type_to_json_schema(List[str])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_parameterized_dict_still_works(self):
        """Dict[str, int] still generates correct additionalProperties."""
        result = _type_to_json_schema(Dict[str, int])
        assert result == {"type": "object", "additionalProperties": {"type": "integer"}}

    def test_function_with_bare_list_param(self):
        """A function with bare `list` param produces schema with 'items'."""

        def process_items(items: list) -> str:
            return str(items)

        result = schema_from_function(process_items)
        items_schema = result["input"]["properties"]["items"]
        assert items_schema == {"type": "array", "items": {}}

    def test_function_with_bare_dict_param(self):
        """A function with bare `dict` param produces schema with 'additionalProperties'."""

        def process_data(data: dict) -> str:
            return str(data)

        result = schema_from_function(process_data)
        data_schema = result["input"]["properties"]["data"]
        assert data_schema == {"type": "object", "additionalProperties": {}}


class TestStringAnnotations:
    """Test BUG-P2-07: PEP 563 string annotations are resolved correctly."""

    def test_string_dict_str_float(self):
        result = _type_to_json_schema("Dict[str, float]")
        assert result == {"type": "object", "additionalProperties": {"type": "number"}}

    def test_string_list_int(self):
        result = _type_to_json_schema("List[int]")
        assert result == {"type": "array", "items": {"type": "integer"}}

    def test_string_optional_str(self):
        result = _type_to_json_schema("Optional[str]")
        assert result == {"type": "string"}

    def test_string_basic_str(self):
        result = _type_to_json_schema("str")
        assert result == {"type": "string"}

    def test_string_basic_int(self):
        result = _type_to_json_schema("int")
        assert result == {"type": "integer"}

    def test_unresolvable_string(self):
        result = _type_to_json_schema("SomeUnknownType")
        assert result == {}

    def test_string_dict_str_any(self):
        result = _type_to_json_schema("Dict[str, Any]")
        assert result == {"type": "object", "additionalProperties": {}}
