# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool registry — name lookup with alias resolution.

The registry is intentionally tiny. Plugin/MCP tool servers, deferred-
loading, and namespace policies all sit on top of this — they belong in
follow-on layers, not in the core registry.

External tools should be namespaced (e.g. ``mcp_<server>_<tool>``) so they
cannot shadow built-ins. The registry rejects exact name collisions: the
caller is responsible for resolving them deterministically.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..errors import HarnessConfigError
from .contract import Tool


class ToolRegistry:
    """Lookup tools by name or alias.

    Order is preserved on insertion so the provider client can serialize
    tools in a deterministic order — important for prompt-cache stability
    (design §17).
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._aliases: Dict[str, str] = {}  # alias → canonical name

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise HarnessConfigError(
                f"Duplicate tool name {tool.name!r}: refusing to register."
            )
        for alias in tool.aliases:
            if alias in self._tools or alias in self._aliases:
                raise HarnessConfigError(
                    f"Tool {tool.name!r} alias {alias!r} collides with an existing name/alias."
                )
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            self._aliases[alias] = tool.name

    def register_all(self, tools: List[Tool]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Optional[Tool]:
        """Resolve by name or alias. Returns ``None`` if not found."""
        if name in self._tools:
            return self._tools[name]
        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._tools[canonical]
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def all(self) -> List[Tool]:
        """Return tools in insertion order."""
        return list(self._tools.values())

    def enabled(self) -> List[Tool]:
        return [t for t in self._tools.values() if t.is_enabled()]
