# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``update_plan`` — maintain a visible plan/todo list across the session."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..contract import Tool, ToolResult, ToolUseContext


class UpdatePlan(Tool[Dict[str, Any], List[Dict[str, Any]]]):
    @property
    def name(self) -> str:
        return "update_plan"

    @property
    def description(self) -> str:
        return (
            "Replace the current visible plan/todo list. Each step has "
            "{description, status: 'pending'|'in_progress'|'completed'}. "
            "The model should call this whenever its plan changes."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": (
                        "Ordered list of plan steps. Each entry should be an "
                        "object with {description, status: pending|in_progress|completed}."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "status": {"type": "string"},
                        },
                    },
                }
            },
            "required": ["steps"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False  # state mutation, but no destructive effect

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(
        self,
        input: Dict[str, Any],
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[List[Dict[str, Any]]]:
        steps = input.get("steps") or []
        if not isinstance(steps, list):
            return ToolResult.error("steps must be a list")
        # Normalize and store on the session store. Accept plain strings or
        # {description, status} objects; anything else is an error so the
        # model gets a clear schema-correction message instead of silent loss.
        normalized = []
        for i, s in enumerate(steps):
            if isinstance(s, str):
                normalized.append({"description": s, "status": "pending"})
            elif isinstance(s, dict):
                normalized.append(
                    {
                        "description": str(s.get("description", "")),
                        "status": s.get("status", "pending"),
                    }
                )
            else:
                return ToolResult.error(
                    f"step {i}: must be a string or {{description, status}} object"
                )
        context.store["plan"] = normalized
        rendered = "\n".join(
            f"  [{s['status']}] {s['description']}" for s in normalized
        )
        return ToolResult.ok(
            content=f"Plan updated ({len(normalized)} steps):\n{rendered}",
            output=normalized,
        )
