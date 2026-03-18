# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for agentspan.agents.runtime.discovery."""

import sys
import types

import pytest
from unittest.mock import patch

from agentspan.agents.agent import Agent
from agentspan.agents.runtime.discovery import discover_agents, _scan_module


class TestScanModule:
    def test_finds_agent_instances(self):
        mod = types.ModuleType("fake_mod")
        a1 = Agent(name="bot1", model="openai/gpt-4o")
        a2 = Agent(name="bot2", model="openai/gpt-4o")
        mod.bot1 = a1
        mod.bot2 = a2
        mod.some_string = "not an agent"
        out, seen = [], set()
        _scan_module(mod, Agent, out, seen)
        assert len(out) == 2
        assert {a.name for a in out} == {"bot1", "bot2"}

    def test_skips_private_attrs(self):
        mod = types.ModuleType("fake_mod")
        mod._hidden = Agent(name="hidden", model="openai/gpt-4o")
        out, seen = [], set()
        _scan_module(mod, Agent, out, seen)
        assert len(out) == 0

    def test_deduplicates_by_name(self):
        mod = types.ModuleType("fake_mod")
        a = Agent(name="same", model="openai/gpt-4o")
        mod.a1 = a
        mod.a2 = a  # same object, same name
        out, seen = [], set()
        _scan_module(mod, Agent, out, seen)
        assert len(out) == 1

    def test_ignores_non_agent_objects(self):
        mod = types.ModuleType("fake_mod")
        mod.number = 42
        mod.text = "hello"
        mod.a_list = [1, 2, 3]
        out, seen = [], set()
        _scan_module(mod, Agent, out, seen)
        assert len(out) == 0


class TestDiscoverAgents:
    def test_discovers_from_single_module(self):
        mod = types.ModuleType("myapp.agents")
        mod.assistant = Agent(name="assistant", model="openai/gpt-4o")
        with patch("importlib.import_module", return_value=mod):
            result = discover_agents(["myapp.agents"])
        assert len(result) == 1
        assert result[0].name == "assistant"

    def test_warns_on_import_error(self):
        with patch("importlib.import_module", side_effect=ImportError("nope")):
            result = discover_agents(["nonexistent.pkg"])
        assert result == []

    def test_discovers_from_multiple_packages(self):
        mod1 = types.ModuleType("pkg1")
        mod1.a = Agent(name="agent_a", model="openai/gpt-4o")
        mod2 = types.ModuleType("pkg2")
        mod2.b = Agent(name="agent_b", model="openai/gpt-4o")

        def import_side_effect(name):
            return {"pkg1": mod1, "pkg2": mod2}[name]

        with patch("importlib.import_module", side_effect=import_side_effect):
            result = discover_agents(["pkg1", "pkg2"])
        assert len(result) == 2
        assert {a.name for a in result} == {"agent_a", "agent_b"}

    def test_empty_packages_list(self):
        result = discover_agents([])
        assert result == []

    def test_deduplicates_across_packages(self):
        """Same agent name in two packages should only appear once."""
        mod1 = types.ModuleType("pkg1")
        mod1.bot = Agent(name="shared_bot", model="openai/gpt-4o")
        mod2 = types.ModuleType("pkg2")
        mod2.bot = Agent(name="shared_bot", model="openai/gpt-4o")

        def import_side_effect(name):
            return {"pkg1": mod1, "pkg2": mod2}[name]

        with patch("importlib.import_module", side_effect=import_side_effect):
            result = discover_agents(["pkg1", "pkg2"])
        assert len(result) == 1
