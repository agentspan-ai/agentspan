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
    from autopilot.integrations.github.tools import get_tools as github_tools
    from autopilot.integrations.slack.tools import get_tools as slack_tools
    from autopilot.integrations.google_calendar.tools import get_tools as gcal_tools
    from autopilot.integrations.google_drive.tools import get_tools as gdrive_tools
    from autopilot.integrations.s3.tools import get_tools as s3_tools
    from autopilot.integrations.gmail.tools import get_tools as gmail_tools
    from autopilot.integrations.outlook.tools import get_tools as outlook_tools
    from autopilot.integrations.linear.tools import get_tools as linear_tools
    from autopilot.integrations.jira.tools import get_tools as jira_tools
    from autopilot.integrations.notion.tools import get_tools as notion_tools
    from autopilot.integrations.hubspot.tools import get_tools as hubspot_tools
    from autopilot.integrations.salesforce.tools import get_tools as salesforce_tools
    from autopilot.integrations.google_analytics.tools import get_tools as ga_tools
    from autopilot.integrations.whatsapp.tools import get_tools as whatsapp_tools
    from autopilot.integrations.imessage.tools import get_tools as imessage_tools

    registry.register("local_fs", local_fs_tools)
    registry.register("web_search", web_search_tools)
    registry.register("doc_reader", doc_reader_tools)
    registry.register("github", github_tools)
    registry.register("slack", slack_tools)
    registry.register("google_calendar", gcal_tools)
    registry.register("google_drive", gdrive_tools)
    registry.register("s3", s3_tools)
    registry.register("gmail", gmail_tools)
    registry.register("outlook", outlook_tools)
    registry.register("linear", linear_tools)
    registry.register("jira", jira_tools)
    registry.register("notion", notion_tools)
    registry.register("hubspot", hubspot_tools)
    registry.register("salesforce", salesforce_tools)
    registry.register("google_analytics", ga_tools)
    registry.register("whatsapp", whatsapp_tools)
    registry.register("imessage", imessage_tools)
