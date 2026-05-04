# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for hybrid agent transfer worker registration (issue #38).

A hybrid agent has both tools[] AND agents[] with HANDOFF strategy.
The server compiles transfer tools (e.g. manager_transfer_to_researcher)
as SIMPLE Conductor tasks.  Without registered Python workers for them,
those tasks wait forever — deadlock.
"""

import asyncio

import pytest
from unittest.mock import patch

from agentspan.agents.agent import Agent
from agentspan.agents.tool import tool


class TestGetRequiredWorkerNamesHybrid:
    """_collect_worker_names must include transfer tool names for hybrid agents."""

    def _call(self, agent):
        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        # Pass required_workers=None to exercise the fallback detection path
        return rt._collect_worker_names(agent, required_workers=None)

    def test_hybrid_includes_check_transfer(self):
        @tool
        def calculate(x: int) -> int:
            """Add one."""
            return x + 1

        mgr = Agent(name="manager", model="openai/gpt-4o", tools=[calculate])
        mgr.agents = [Agent(name="researcher", model="openai/gpt-4o")]

        names = self._call(mgr)
        assert "manager_check_transfer" in names

    def test_hybrid_includes_transfer_to_workers(self):
        @tool
        def search(q: str) -> str:
            """Search."""
            return q

        mgr = Agent(name="manager", model="openai/gpt-4o", tools=[search])
        sub1 = Agent(name="researcher", model="openai/gpt-4o")
        sub2 = Agent(name="writer", model="openai/gpt-4o")
        mgr.agents = [sub1, sub2]

        names = self._call(mgr)
        assert "manager_transfer_to_researcher" in names
        assert "manager_transfer_to_writer" in names

    def test_non_hybrid_no_transfer_workers(self):
        # Only tools, no sub-agents — not hybrid
        @tool
        def ping() -> str:
            """Ping."""
            return "pong"

        agent = Agent(name="solo", model="openai/gpt-4o", tools=[ping])
        names = self._call(agent)
        assert not any("_transfer_to_" in n for n in names)

    def test_pure_subagents_no_transfer_workers(self):
        # Sub-agents but no tools — not hybrid
        mgr = Agent(name="mgr", model="openai/gpt-4o")
        mgr.agents = [Agent(name="sub", model="openai/gpt-4o")]

        names = self._call(mgr)
        assert not any("_transfer_to_" in n for n in names)


class TestRegisterHybridTransferWorkers:
    """_register_hybrid_transfer_workers must register one worker per sub-agent."""

    def test_registers_worker_for_each_sub_agent(self):
        @tool
        def lookup(k: str) -> str:
            """Look up."""
            return k

        mgr = Agent(name="manager", model="openai/gpt-4o", tools=[lookup])
        mgr.agents = [
            Agent(name="researcher", model="openai/gpt-4o"),
            Agent(name="writer", model="openai/gpt-4o"),
        ]

        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)

        registered = []

        def fake_worker_task(**kwargs):
            registered.append(kwargs["task_definition_name"])
            return lambda fn: fn

        with patch("conductor.client.worker.worker_task.worker_task", side_effect=fake_worker_task):
            rt._register_hybrid_transfer_workers(mgr, domain=None)

        assert "manager_transfer_to_researcher" in registered
        assert "manager_transfer_to_writer" in registered
        assert len(registered) == 2

    def test_transfer_worker_returns_empty_dict(self):
        """The no-op transfer worker must return {} so LLM sees a valid tool result."""

        @tool
        def run(cmd: str) -> str:
            """Run."""
            return cmd

        mgr = Agent(name="manager", model="openai/gpt-4o", tools=[run])
        mgr.agents = [Agent(name="researcher", model="openai/gpt-4o")]

        from agentspan.agents.runtime.runtime import AgentRuntime

        rt = AgentRuntime.__new__(AgentRuntime)
        captured_fn = {}

        def fake_worker_task(**kwargs):
            name = kwargs["task_definition_name"]

            def decorator(fn):
                captured_fn[name] = fn
                return fn

            return decorator

        with patch("conductor.client.worker.worker_task.worker_task", side_effect=fake_worker_task):
            rt._register_hybrid_transfer_workers(mgr, domain=None)

        assert "manager_transfer_to_researcher" in captured_fn
        result = asyncio.get_event_loop().run_until_complete(
            captured_fn["manager_transfer_to_researcher"]()
        )
        assert result == {}

    def test_workers_called_in_register_workers_for_hybrid(self):
        """_register_workers must invoke _register_hybrid_transfer_workers for hybrid agents."""

        @tool
        def fetch(url: str) -> str:
            """Fetch."""
            return url

        mgr = Agent(name="manager", model="openai/gpt-4o", tools=[fetch])
        mgr.agents = [Agent(name="researcher", model="openai/gpt-4o")]

        from agentspan.agents.runtime.runtime import AgentRuntime
        from agentspan.agents.runtime.tool_registry import ToolRegistry

        rt = AgentRuntime.__new__(AgentRuntime)

        called_with = []

        def capture(agent, **kw):
            called_with.append(agent)

        rt._register_hybrid_transfer_workers = capture

        # Patch out Conductor calls so the test stays unit-level
        with patch.object(rt, "_register_check_transfer_worker"):
            with patch.object(ToolRegistry, "register_tool_workers", return_value=None):
                rt._register_workers(
                    mgr,
                    required_workers={"manager_check_transfer"},
                    domain=None,
                )

        assert mgr in called_with, "_register_hybrid_transfer_workers was not called for hybrid agent"
