# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for AgentRuntime._collect_registered_pairs."""

from agentspan.agents import Agent, tool
from agentspan.agents.runtime.runtime import AgentRuntime


@tool
def stateful_tool(x: str) -> str:
    """A tool."""
    return x


@tool
def stateless_tool(y: str) -> str:
    """Another tool."""
    return y


def test_pairs_include_domain_for_stateful_agent_tools(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)  # avoid full init
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=True, tools=[stateful_tool]
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateful_tool", "d1") in pairs


def test_pairs_use_passed_domain_for_all_tools_in_stateful_run(monkeypatch):
    """Worker domain contract: when ``domain`` is non-None (the run is
    stateful), EVERY worker tool registers under that domain — including
    non-stateful ones. The earlier policy (``None`` for non-stateful
    tools even in a stateful run) caused workflow ``4e0d2953`` to stall.
    See ``docs/design/WORKER_DOMAIN_CONTRACT.md``."""
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=False, tools=[stateless_tool]
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateless_tool", "d1") in pairs


def test_pairs_use_none_domain_for_stateless_run(monkeypatch):
    """Companion to the above: when ``domain`` is None (the run is
    NOT stateful), non-stateful tools register with no domain."""
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=False, tools=[stateless_tool]
    )
    pairs = rt._collect_registered_pairs(agent, domain=None)
    assert ("stateless_tool", None) in pairs


def test_pairs_recurse_into_sub_agents(monkeypatch):
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    sub = Agent(
        name="sub", model="openai/gpt-4o-mini", stateful=True, tools=[stateful_tool]
    )
    parent = Agent(name="parent", model="openai/gpt-4o-mini", agents=[sub])
    pairs = rt._collect_registered_pairs(parent, domain="d1")
    assert ("stateful_tool", "d1") in pairs


def test_pairs_skip_non_worker_tool_types(monkeypatch):
    """http/mcp/human/agent_tool tools are server-side; no Python worker."""
    monkeypatch.setenv("AGENTSPAN_AUTO_START_SERVER", "false")
    rt = AgentRuntime.__new__(AgentRuntime)
    from agentspan.agents.tool import http_tool

    h = http_tool(
        name="my_http", description="x", url="https://example.com",
    )
    agent = Agent(
        name="A", model="openai/gpt-4o-mini", stateful=True,
        tools=[h, stateful_tool],
    )
    pairs = rt._collect_registered_pairs(agent, domain="d1")
    assert ("stateful_tool", "d1") in pairs
    assert all(name != "my_http" for name, _ in pairs)
