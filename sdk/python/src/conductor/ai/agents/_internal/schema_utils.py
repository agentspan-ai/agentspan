# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""JSON Schema generation from Python type hints, Pydantic models, and dataclasses.

Wraps ``conductor.client.automator.json_schema_generator`` and adds support
for Pydantic ``BaseModel`` classes.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, get_type_hints

# ── Type-hint → JSON Schema mapping ────────────────────────────────────

_PYTHON_TYPE_TO_JSON = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array", "items": {}},
    dict: {"type": "object", "additionalProperties": {}},
    type(None): {"type": "null"},
}


def _resolve_string_annotation(annotation: str) -> Any:
    """Attempt to resolve a PEP 563 string annotation to an actual type."""
    import typing

    ns = {
        **vars(typing),
        "dict": dict,
        "list": list,
        "set": set,
        "tuple": tuple,
        "frozenset": frozenset,
        "type": type,
    }
    try:
        return eval(annotation, ns)  # noqa: S307
    except Exception:
        return None


def _type_to_json_schema(annotation: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}

    # Handle PEP 563 string annotations
    if isinstance(annotation, str):
        resolved = _resolve_string_annotation(annotation)
        if resolved is not None:
            return _type_to_json_schema(resolved)
        return {}

    # Direct mapping
    if annotation in _PYTHON_TYPE_TO_JSON:
        return dict(_PYTHON_TYPE_TO_JSON[annotation])

    # Handle Optional[X] (Union[X, None])
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    if origin is type(None):
        return {"type": "null"}

    # Union types (including Optional)
    import typing

    if origin is getattr(typing, "Union", None):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_json_schema(non_none[0])
        return {}

    # List[X]
    if origin is list:
        schema: Dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _type_to_json_schema(args[0])
        return schema

    # Dict[str, X]
    if origin is dict:
        schema = {"type": "object"}
        if len(args) >= 2:
            schema["additionalProperties"] = _type_to_json_schema(args[1])
        return schema

    return {}


# ── Function → JSON Schema ─────────────────────────────────────────────


def schema_from_function(func: Callable[..., Any]) -> Dict[str, Any]:
    """Generate input/output JSON Schemas from a Python function's signature.

    Uses type hints and docstring to produce schemas compatible with
    Conductor's ``ToolSpec.input_schema``.

    Args:
        func: The function to analyse.

    Returns:
        A dict with ``"input"`` and ``"output"`` keys, each containing a
        JSON Schema dict.
    """
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    # Build input schema
    properties: Dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "context"):
            continue

        prop = _type_to_json_schema(hints.get(name, param.annotation))
        if not prop:
            prop = {}

        # Use docstring for parameter descriptions (simple extraction)
        properties[name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(name)

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        input_schema["required"] = required

    # Build output schema
    return_type = hints.get("return", sig.return_annotation)
    output_schema = (
        _type_to_json_schema(return_type) if return_type is not inspect.Parameter.empty else {}
    )

    return {"input": input_schema, "output": output_schema}


def schema_from_pydantic(model_class: type) -> Dict[str, Any]:
    """Generate a JSON Schema from a Pydantic ``BaseModel`` class.

    Args:
        model_class: A Pydantic ``BaseModel`` subclass.

    Returns:
        The JSON Schema dict produced by Pydantic's ``model_json_schema()``.

    Raises:
        TypeError: If *model_class* is not a Pydantic ``BaseModel``.
    """
    if hasattr(model_class, "model_json_schema"):
        # Pydantic v2
        return model_class.model_json_schema()
    elif hasattr(model_class, "schema"):
        # Pydantic v1
        return model_class.schema()
    raise TypeError(f"{model_class} is not a Pydantic BaseModel")
