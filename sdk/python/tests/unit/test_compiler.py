# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for internal utilities (model parser, schema generation)."""

import pytest

from conductor.ai.agents._internal.model_parser import ParsedModel, parse_model
from conductor.ai.agents._internal.schema_utils import schema_from_function


class TestModelParser:
    """Test provider/model string parsing."""

    def test_openai(self):
        result = parse_model("openai/gpt-4o")
        assert result == ParsedModel(provider="openai", model="gpt-4o")

    def test_anthropic(self):
        result = parse_model("anthropic/claude-sonnet-4-20250514")
        assert result == ParsedModel(provider="anthropic", model="claude-sonnet-4-20250514")

    def test_azure(self):
        result = parse_model("azure_openai/gpt-4o")
        assert result == ParsedModel(provider="azure_openai", model="gpt-4o")

    def test_no_slash_raises(self):
        with pytest.raises(ValueError, match="Invalid model format"):
            parse_model("gpt-4o")

    def test_empty_provider_raises(self):
        with pytest.raises(ValueError, match="Empty provider"):
            parse_model("/gpt-4o")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="Empty model name"):
            parse_model("openai/")

    def test_model_with_multiple_slashes(self):
        result = parse_model("hugging_face/meta-llama/Llama-3-70b")
        assert result.provider == "hugging_face"
        assert result.model == "meta-llama/Llama-3-70b"


class TestSchemaFromFunction:
    """Test JSON Schema generation from function signatures."""

    def test_basic_types(self):
        def fn(name: str, age: int, score: float, active: bool) -> dict:
            pass

        schema = schema_from_function(fn)
        props = schema["input"]["properties"]
        assert props["name"]["type"] == "string"
        assert props["age"]["type"] == "integer"
        assert props["score"]["type"] == "number"
        assert props["active"]["type"] == "boolean"

    def test_required_params(self):
        def fn(required_param: str, optional_param: str = "default") -> str:
            pass

        schema = schema_from_function(fn)
        assert "required_param" in schema["input"]["required"]
        assert "optional_param" not in schema["input"].get("required", [])

    def test_no_annotations(self):
        def fn(x, y):
            pass

        schema = schema_from_function(fn)
        assert "x" in schema["input"]["properties"]
        assert "y" in schema["input"]["properties"]

    def test_return_type(self):
        def fn() -> str:
            pass

        schema = schema_from_function(fn)
        assert schema["output"]["type"] == "string"

    def test_list_type(self):
        from typing import List

        def fn(items: List[str]) -> list:
            pass

        schema = schema_from_function(fn)
        assert schema["input"]["properties"]["items"]["type"] == "array"

    def test_dict_type(self):
        from typing import Dict

        def fn(data: Dict[str, int]) -> dict:
            pass

        schema = schema_from_function(fn)
        assert schema["input"]["properties"]["data"]["type"] == "object"

    def test_skips_self_cls(self):
        def fn(self, x: str) -> str:
            pass

        schema = schema_from_function(fn)
        assert "self" not in schema["input"]["properties"]
        assert "x" in schema["input"]["properties"]
