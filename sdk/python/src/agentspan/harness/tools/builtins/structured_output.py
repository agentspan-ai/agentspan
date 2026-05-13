# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``structured_output`` — emit a final machine-readable result."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class StructuredOutput(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "structured_output"

    @property
    def description(self) -> str:
        return (
            "Submit the final structured output for this session. The model "
            "calls this once when it has produced the final answer. The "
            "harness records it as the session result."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "description": (
                        "The structured final result. Either pass the result "
                        "object here or pass the fields directly at the top "
                        "level — the harness records whatever is given."
                    ),
                    "additionalProperties": True,
                }
            },
            # ``result`` is intentionally not required: the model can either
            # nest the payload under ``result`` or pass fields at top level.
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[Dict[str, Any]]:
        # Accept either:
        #   {"result": {...}}     — canonical
        #   {"output": {...}}     — common LLM alias
        #   {<fields directly>}   — flat: the whole input becomes the result
        # We strip the conventional aliases so the recorded result doesn't
        # contain confusing duplicate fields.
        result = input.get("result")
        if result is None:
            result = input.get("output")
        if result is None:
            result = {k: v for k, v in input.items() if k not in ("result", "output")}
        context.store["structured_output"] = result
        return ToolResult.ok(
            content="Structured output recorded.",
            output=result,
        )
