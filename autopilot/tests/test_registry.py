"""Tests for IntegrationRegistry."""

from __future__ import annotations

import pytest

from autopilot.registry import IntegrationRegistry, get_default_registry, reset_default_registry


class TestIntegrationRegistry:
    def test_register_and_get_tools(self):
        registry = IntegrationRegistry()
        sentinel = object()
        registry.register("test_integration", lambda: [sentinel])

        tools = registry.get_tools("test_integration")
        assert tools == [sentinel]

    def test_get_tools_unknown_returns_empty(self):
        registry = IntegrationRegistry()
        assert registry.get_tools("nonexistent") == []

    def test_list_integrations(self):
        registry = IntegrationRegistry()
        registry.register("zebra", lambda: [])
        registry.register("alpha", lambda: [])

        names = registry.list_integrations()
        assert names == ["alpha", "zebra"]

    def test_reset_clears_all(self):
        registry = IntegrationRegistry()
        registry.register("something", lambda: ["x"])
        registry.reset()

        assert registry.list_integrations() == []
        assert registry.get_tools("something") == []

    def test_register_overwrites(self):
        registry = IntegrationRegistry()
        registry.register("dup", lambda: ["first"])
        registry.register("dup", lambda: ["second"])

        assert registry.get_tools("dup") == ["second"]


class TestDefaultRegistry:
    def test_default_registry_has_builtins(self):
        registry = get_default_registry()
        names = registry.list_integrations()

        assert "local_fs" in names
        assert "web_search" in names
        assert "doc_reader" in names

    def test_default_registry_is_singleton(self):
        a = get_default_registry()
        b = get_default_registry()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_default_registry()
        reset_default_registry()
        b = get_default_registry()
        assert a is not b
