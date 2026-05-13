# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""``shared_store_read`` / ``shared_store_write`` — cross-subagent state."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


def _store(context: ToolUseContext):
    return context.store.get("shared_store")


class SharedStoreWrite(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "shared_store_write"

    @property
    def description(self) -> str:
        return (
            "Persist a structured value (JSON) under a named key in the "
            "session's shared store. Visible to subagents and on resume."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"description": "Any JSON-serializable value."},
            },
            "required": ["key", "value"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    async def call(self, input, context, parent_message=None, on_progress=None):
        store = _store(context)
        if store is None:
            return ToolResult.error("no shared_store configured for this session")
        path = store.write(input["key"], input["value"])
        return ToolResult.ok(content=f"wrote {input['key']} → {path}", output={"path": path})


class SharedStoreRead(Tool[Dict[str, Any], Any]):
    @property
    def name(self) -> str:
        return "shared_store_read"

    @property
    def description(self) -> str:
        return "Read a value previously written via shared_store_write. Returns null if absent."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        store = _store(context)
        if store is None:
            return ToolResult.error("no shared_store configured for this session")
        value = store.read(input["key"])
        return ToolResult.ok(
            content=str(value)[:4000] if value is not None else "[absent]",
            output=value,
        )


class SharedStoreList(Tool[Dict[str, Any], list]):
    @property
    def name(self) -> str:
        return "shared_store_list"

    @property
    def description(self) -> str:
        return "List all keys currently in the shared store."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        store = _store(context)
        if store is None:
            return ToolResult.error("no shared_store configured for this session")
        keys = store.list()
        return ToolResult.ok(content=", ".join(keys) or "[empty]", output=keys)
