"""IntegrationRegistry — manages builtin and custom integration tool sets."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class IntegrationRegistry:
    """Registry for integration tool providers.

    Each integration is registered under a name and provides a
    ``get_tools()`` callable that returns a list of @tool-decorated functions.
    """

    def __init__(self) -> None:
        self._integrations: Dict[str, Callable[[], List[Any]]] = {}

    def register(self, name: str, get_tools_fn: Callable[[], List[Any]]) -> None:
        """Register an integration's tool provider.

        Args:
            name: Integration name (e.g. ``"local_fs"``).
            get_tools_fn: Callable returning a list of @tool-decorated functions.
        """
        self._integrations[name] = get_tools_fn

    def get_tools(self, name: str) -> List[Any]:
        """Retrieve tools for a named integration.

        Args:
            name: Integration name.

        Returns:
            List of @tool-decorated functions, or empty list if not found.
        """
        fn = self._integrations.get(name)
        if fn is None:
            return []
        return fn()

    def list_integrations(self) -> List[str]:
        """Return sorted list of registered integration names."""
        return sorted(self._integrations.keys())

    def reset(self) -> None:
        """Clear all registrations. Used for test isolation."""
        self._integrations.clear()


# -- Singleton ----------------------------------------------------------------

_default_registry: Optional[IntegrationRegistry] = None


def get_default_registry() -> IntegrationRegistry:
    """Return the singleton registry, creating and populating it on first call."""
    global _default_registry
    if _default_registry is None:
        _default_registry = IntegrationRegistry()
        _register_builtins(_default_registry)
    return _default_registry


def reset_default_registry() -> None:
    """Reset the singleton so the next call re-creates it. For testing."""
    global _default_registry
    _default_registry = None


def _register_builtins(registry: IntegrationRegistry) -> None:
    """Register all built-in integrations."""
    from autopilot.integrations.local_fs.tools import get_tools as local_fs_tools
    from autopilot.integrations.web_search.tools import get_tools as web_search_tools
    from autopilot.integrations.doc_reader.tools import get_tools as doc_reader_tools

    registry.register("local_fs", local_fs_tools)
    registry.register("web_search", web_search_tools)
    registry.register("doc_reader", doc_reader_tools)
