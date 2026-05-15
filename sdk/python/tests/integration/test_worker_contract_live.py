"""End-to-end worker domain contract verification against a real server.

Unit tests in ``tests/unit/test_worker_contract.py`` assert SDK-side
internal consistency. They cannot catch divergence between SDK and
server (the cf1cfecf failure mode: SDK and tests both happy, server
schedules the task on a different domain than the SDK registered).

This file closes that gap. For a small set of agent-tree shapes that
hit the worker domain contract's edge cases, we:

  1. Start the workflow against the live server (``rt.start``).
  2. Fetch the actual ``taskToDomain`` Conductor stamped on the workflow.
  3. Walk locally registered ``(name, domain)`` pairs.
  4. Assert: every server ``(name, domain)`` entry has a matching SDK pair.

If the server's policy ever drifts from the SDK's (the historical
pattern), this test fails immediately on a real server roundtrip — long
before the user's actual agent has a chance to stall.
"""

import os
import time

import pytest
import requests

from agentspan.agents import Agent, AgentRuntime, Strategy, tool

_SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
_CONDUCTOR_BASE = _SERVER_URL.rstrip("/").replace("/api", "")

pytestmark = pytest.mark.integration


def _verify_contract_against_live_server(rt, agent, prompt: str) -> dict:
    """Start the agent, wait for taskToDomain to land, fetch from server,
    and assert SDK-registered pairs cover every server-emitted pair.
    Returns the workflow JSON for further assertions."""
    handle = rt.start(agent, prompt)
    time.sleep(1.5)  # let server populate taskToDomain
    wf = requests.get(
        f"{_CONDUCTOR_BASE}/api/workflow/{handle.execution_id}",
        timeout=10,
    ).json()
    server_ttd: dict = wf.get("taskToDomain", {}) or {}
    expected_pairs = set(server_ttd.items())

    # The SDK runtime carries the pairs it registered for this agent.
    # Pull them via the same helper the contract unit test uses.
    domain = next(iter(server_ttd.values())) if server_ttd else None
    registered_pairs = set(rt._collect_registered_pairs(agent, domain))

    missing = expected_pairs - registered_pairs
    assert not missing, (
        f"Live worker domain contract violation: server scheduled "
        f"{sorted(missing)} but SDK has no matching registered worker.\n"
        f"  server taskToDomain:    {sorted(expected_pairs)}\n"
        f"  SDK registered pairs:   {sorted(registered_pairs)}\n"
        f"  execution_id:           {handle.execution_id}\n"
        f"This would cause the historical 'task SCHEDULED, no poller' "
        f"hang. See docs/design/WORKER_DOMAIN_CONTRACT.md."
    )
    return wf


# ── End-to-end fixtures matching the historical bug shapes ────────────


class TestWorkerContractLiveServer:
    """Integration-level proof: server and SDK agree on (name, domain)
    pairs for every shape that hit a historical regression. If a future
    SDK or server change breaks the agreement, ``rt.start`` returns a
    workflow whose ``taskToDomain`` doesn't match what the SDK
    registered, and the assertion in
    ``_verify_contract_against_live_server`` fails.
    """

    def test_cf1cfecf_non_stateful_tool_dynamic_dispatch(self):
        """Reproduces the cf1cfecf shape: a non-stateful tool
        (``run_command``) on an agent that's stateful via a sibling
        stateful tool. Server must include both in taskToDomain so the
        LLM-loop dynamic dispatch finds a worker poller."""
        @tool
        def run_command(command: str) -> str:
            return f"ran: {command}"

        @tool(stateful=True)
        def write_implementation_report(content: str) -> str:
            return "wrote"

        a = Agent(
            name="contract_live_cf1cfecf",
            model="openai/gpt-4o-mini",
            instructions="Use the tools.",
            stateful=True,
            tools=[run_command, write_implementation_report],
            max_turns=1,
        )
        with AgentRuntime() as rt:
            wf = _verify_contract_against_live_server(rt, a, "say hi")

        ttd = wf.get("taskToDomain", {})
        assert "run_command" in ttd, (
            "non-stateful tool MUST appear in taskToDomain — otherwise the "
            "LLM-loop dynamic dispatch (FORK_JOIN_DYNAMIC) schedules with "
            "no domain while the SDK has the worker on the run domain."
        )
        assert "write_implementation_report" in ttd

    def test_b38024fb_prefill_only_tool(self):
        """Tool that only appears in prefill_tools. Server must include
        it in taskToDomain (via static SIMPLE collection) and SDK must
        register the worker under the same domain."""
        @tool
        def read_repo_docs() -> str:
            return "docs"

        @tool(stateful=True)
        def write_implementation_report(content: str) -> str:
            return "wrote"

        a = Agent(
            name="contract_live_b38024fb",
            model="openai/gpt-4o-mini",
            instructions="Use the tools.",
            stateful=True,
            tools=[write_implementation_report],
            prefill_tools=[read_repo_docs.call()],
            max_turns=1,
        )
        with AgentRuntime() as rt:
            wf = _verify_contract_against_live_server(rt, a, "say hi")

        ttd = wf.get("taskToDomain", {})
        assert "read_repo_docs" in ttd, (
            "prefill-only non-stateful tool MUST appear in taskToDomain — "
            "the prefill SIMPLE task is scheduled with that domain."
        )

    def test_0f715217_pae_named_slot(self):
        """PAE harness with a stateful tool inside the planner sub-agent
        (named slot, not in agents=). Server must walk the named slot
        and include the planner's tools in taskToDomain."""
        @tool(stateful=True)
        def planner_stateful_tool() -> str:
            return "planner state"

        @tool
        def harness_tool() -> str:
            return "h"

        planner = Agent(
            name="contract_live_0f715217_planner",
            model="openai/gpt-4o-mini",
            instructions="plan",
            tools=[planner_stateful_tool],
        )
        coder = Agent(
            name="contract_live_0f715217",
            model="openai/gpt-4o-mini",
            strategy=Strategy.PLAN_EXECUTE,
            planner=planner,
            tools=[harness_tool],
        )
        with AgentRuntime() as rt:
            wf = _verify_contract_against_live_server(rt, coder, "anything")

        ttd = wf.get("taskToDomain", {})
        assert "planner_stateful_tool" in ttd, (
            "Stateful tool inside PAE planner sub-agent MUST appear in "
            "taskToDomain — server must walk planner/fallback named slots."
        )
