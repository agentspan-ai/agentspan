# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""End-to-end test for PAC tool-type routing.

Drives ``Strategy.PLAN_EXECUTE`` against a live agentspan server with a typed
Plan that mixes four tool types in one workflow:

  - 2 × ``mcp``        tools (mcp-testkit math_add + string_uppercase)
  - 1 × ``agent_tool`` (sub-agent prompt-locked to return ``AGENT_OK``)
  - 1 × ``worker``     tool (Python @tool — the deterministic synthesizer)

Three layers of validation, all algorithmic — no LLM-as-judge per CLAUDE.md:

  PROOF 1 (compiled-shape):
      Walks PAC's ``outputData.workflowDef`` and asserts the exact
      Conductor task type each tool routed to:
        mcp_static_tool       → CALL_MCP_TOOL
        agent_tool wrapper    → SUB_WORKFLOW + subWorkflowParam
        @tool worker          → SIMPLE
        parallel=True step    → FORK_JOIN

  PROOF 2 (deterministic execution):
      Asserts the synthesizer's final string contains literal substrings
      ``math=42.0``, ``upper=HELLO``, ``agent=AGENT_OK``. mcp-testkit
      returns fixed values (deterministic); the sub-agent is prompt-locked
      with temperature=0 to return a single token. The check is substring
      match, NOT LLM judging.

  PROOF 3 (per-task COMPLETED):
      Pulls the compiled sub-workflow execution from Conductor and
      asserts every routed task transitioned to status=COMPLETED.

Requirements (the test SKIPs cleanly if either is absent):
  - agentspan server reachable at ``AGENTSPAN_SERVER_URL`` (default
    http://localhost:6767/api) with the PAC tool-type routing fix
  - mcp-testkit running on http://localhost:3001/mcp
    (``uv run mcp-testkit --transport http --port 3001``)

This is a *system-level* test for the PAC routing fix. The PAC unit
layer (server/src/test/.../PlanAndCompileTaskTest) covers the same
routing without a live server.
"""

from __future__ import annotations

import os

import pytest
import requests

from conductor.ai.agents import Agent, AgentRuntime, plan_execute, tool
from conductor.ai.agents.plans import Op, Plan, Step
from conductor.ai.agents.tool import ToolDef, agent_tool

pytestmark = pytest.mark.integration

AGENTSPAN_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
CONDUCTOR_BASE = AGENTSPAN_URL.replace("/api", "")
MCP_URL = "http://localhost:3001/mcp"


def _agentspan_up() -> bool:
    try:
        return requests.get(f"{AGENTSPAN_URL}/metadata/workflow", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _mcp_up() -> bool:
    # MCP servers reject plain GETs with 406 (Not Acceptable); that's a
    # signal it's up and speaking MCP. Anything that connects counts.
    try:
        r = requests.get(MCP_URL, timeout=2)
        return r.status_code in (200, 405, 406)
    except Exception:  # noqa: BLE001
        return False


# ── Tool defs (shared between fixtures and the test body) ─────────────


def _mcp_static_tool(name: str, description: str, input_schema: dict) -> ToolDef:
    """One ToolDef per remote MCP tool so PAC's name→ToolConfig lookup
    can route each op to its own CALL_MCP_TOOL with the matching method.
    """
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="mcp",
        config={"server_url": MCP_URL},
    )


math_add = _mcp_static_tool(
    "math_add",
    "Add two numbers via mcp-testkit.",
    {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
)

string_uppercase = _mcp_static_tool(
    "string_uppercase",
    "Uppercase a string via mcp-testkit.",
    {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
)

mini_agent = Agent(
    name="mini_agent_e2e",
    model=os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini"),
    instructions=(
        "Reply with EXACTLY the single token 'AGENT_OK' and nothing else. "
        "No punctuation, no whitespace, no preamble, no explanation."
    ),
    max_turns=2,
    max_tokens=32,
    temperature=0.0,
)


@tool
def stitch_e2e(math_result: object, upper_result: object, agent_result: object) -> str:
    """Deterministic synthesizer — typed ``object`` so the Conductor-
    threaded MCP payloads (numbers + strings) all coerce cleanly to str.
    """
    return f"math={math_result!s}|upper={upper_result!s}|agent={agent_result!s}"


# ── Helpers to inspect what PAC actually compiled ─────────────────────


def _fetch_workflow(execution_id: str) -> dict:
    r = requests.get(
        f"{CONDUCTOR_BASE}/api/workflow/{execution_id}",
        params={"includeTasks": "true"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _find_pac_output(parent_id: str) -> dict:
    """Return PAC's PLAN_AND_COMPILE task outputData (which embeds the
    compiled WorkflowDef). PAC compiles a fresh def per execution and
    emits it here; the /metadata endpoint only returns the up-front
    placeholder."""
    seen: set[str] = set()
    pending = [parent_id]
    while pending:
        wf_id = pending.pop()
        if wf_id in seen:
            continue
        seen.add(wf_id)
        wf = _fetch_workflow(wf_id)
        for t in wf.get("tasks", []):
            if t.get("taskType") == "PLAN_AND_COMPILE":
                return t.get("outputData") or {}
            sub = t.get("subWorkflowId")
            if sub:
                pending.append(sub)
    raise AssertionError("PLAN_AND_COMPILE task not found in workflow tree")


def _find_compiled_execution(parent_id: str) -> str:
    """Return the execution id of the SUB_WORKFLOW that ran PAC's
    compiled plan (so we can assert each routed task COMPLETED)."""
    wf = _fetch_workflow(parent_id)
    for t in wf.get("tasks", []):
        # The harness names the plan-exec sub-workflow with this suffix.
        if (t.get("referenceTaskName") or "").endswith("_plan_exec"):
            sub = t.get("subWorkflowId")
            if sub:
                return sub
    raise AssertionError("compiled-plan sub-workflow not found")


def _collect_task_types(tasks: list[dict]) -> list[tuple[str, str]]:
    """Depth-first walk of a WorkflowDef.tasks tree returning
    ``[(type, name), ...]``. FORK_JOIN's forkTasks are walked too —
    parallel branches contain the routed tasks."""
    out: list[tuple[str, str]] = []
    for t in tasks:
        out.append((str(t.get("type")), str(t.get("name"))))
        if t.get("type") == "FORK_JOIN":
            for branch in t.get("forkTasks") or []:
                out.extend(_collect_task_types(branch))
    return out


# ── The test ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not _agentspan_up(), reason="agentspan server not running")
@pytest.mark.skipif(not _mcp_up(), reason="mcp-testkit not running on :3001")
def test_pac_toolType_routing_end_to_end() -> None:
    """Single end-to-end run that proves PAC compiles each toolType to
    the right Conductor task type and the resulting plan executes
    deterministically through mcp-testkit + a sub-agent."""

    harness = plan_execute(
        name="pac_routing_e2e",
        tools=[math_add, string_uppercase, agent_tool(mini_agent), stitch_e2e],
        planner_instructions="",  # typed Plan injected; planner output discarded
        model=os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini"),
    )

    plan = Plan(
        steps=[
            Step(
                id="fanout",
                parallel=True,
                operations=[
                    Op("math_add", args={"a": 2, "b": 40}),
                    Op("string_uppercase", args={"text": "hello"}),
                    Op("mini_agent_e2e", args={"request": "Return AGENT_OK"}),
                ],
            ),
            Step(
                id="synthesize",
                depends_on=["fanout"],
                operations=[
                    Op(
                        "stitch_e2e",
                        args={
                            # CALL_MCP_TOOL output → content[0].parsed.result
                            "math_result": "${s_fanout_0.output.content[0].parsed.result}",
                            "upper_result": "${s_fanout_1.output.content[0].parsed.result}",
                            # SUB_WORKFLOW final answer → output.result
                            "agent_result": "${s_fanout_2.output.result}",
                        },
                    ),
                ],
            ),
        ],
    )

    with AgentRuntime() as rt:
        result = rt.run(harness, "(typed Plan injected)", plan=plan)

    assert result.status == "COMPLETED", (
        f"harness must complete; got status={result.status!r}, output={result.output!r}"
    )

    # ── PROOF 1: PAC compiled the right Conductor task per toolType ───
    pac_out = _find_pac_output(result.execution_id)
    assert pac_out.get("error") is None, f"PAC reported a compile error: {pac_out.get('error')!r}"
    wf_def = pac_out["workflowDef"]
    types = _collect_task_types(wf_def.get("tasks") or [])

    mcp_count = sum(1 for t, _ in types if t == "CALL_MCP_TOOL")
    sub_count = sum(1 for t, _ in types if t == "SUB_WORKFLOW")
    stitch_count = sum(1 for t, n in types if t == "SIMPLE" and n == "stitch_e2e")
    fork_count = sum(1 for t, _ in types if t == "FORK_JOIN")

    assert mcp_count == 2, (
        f"two mcp ops must compile to two CALL_MCP_TOOL tasks; "
        f"got {mcp_count}. Full task types: {types}"
    )
    assert sub_count == 1, (
        f"one agent_tool op must compile to one SUB_WORKFLOW task; "
        f"got {sub_count}. Full task types: {types}"
    )
    assert stitch_count == 1, (
        f"one worker op must compile to one SIMPLE 'stitch_e2e' task; "
        f"got {stitch_count}. Full task types: {types}"
    )
    assert fork_count == 1, f"parallel=True step must compile to one FORK_JOIN; got {fork_count}"

    # The agent_tool op must carry a real subWorkflowParam — without it
    # Conductor wouldn't know which child workflow to dispatch.
    fork_task = next(t for t in wf_def["tasks"] if t.get("type") == "FORK_JOIN")
    sub_branch_task = next(
        b[0] for b in fork_task["forkTasks"] if b and b[0].get("type") == "SUB_WORKFLOW"
    )
    swp = sub_branch_task.get("subWorkflowParam") or {}
    assert swp.get("name"), f"SUB_WORKFLOW must declare subWorkflowParam.name; got {swp!r}"
    assert swp.get("version"), f"SUB_WORKFLOW must declare subWorkflowParam.version; got {swp!r}"

    # MCP ops must carry the right shape for Conductor's CallMcpToolTask
    # (mcpServer + method + arguments). Without these the system task
    # has nothing to dispatch.
    mcp_branches = [
        b[0] for b in fork_task["forkTasks"] if b and b[0].get("type") == "CALL_MCP_TOOL"
    ]
    methods_seen = {b["inputParameters"]["method"] for b in mcp_branches}
    assert methods_seen == {"math_add", "string_uppercase"}, (
        f"CALL_MCP_TOOL ops must carry method= each tool name; got {methods_seen!r}"
    )
    for b in mcp_branches:
        ip = b["inputParameters"]
        assert ip["mcpServer"] == MCP_URL, f"mcpServer must thread through cfg; got {ip!r}"
        assert isinstance(ip.get("arguments"), dict)

    # ── PROOF 2: deterministic algorithmic output ─────────────────────
    output_str = str(result.output)
    # mcp-testkit's math_add(2,40) is exactly 42.0 (it returns a JSON
    # number); accept both "42.0" and "42" so a future serialization
    # tweak in mcp-testkit doesn't bit-flip this assertion.
    assert "math=42.0" in output_str or "math=42" in output_str, (
        f"math_add(2,40) must produce 42 in stitched output; got: {output_str!r}"
    )
    assert "upper=HELLO" in output_str, (
        f"string_uppercase('hello') must produce HELLO; got: {output_str!r}"
    )
    assert "agent=AGENT_OK" in output_str, (
        f"mini_agent must return AGENT_OK (prompt-locked, temp=0); got: {output_str!r}"
    )

    # ── PROOF 3: every routed task actually COMPLETED ──────────────────
    sub_exec = _find_compiled_execution(result.execution_id)
    compiled_wf = _fetch_workflow(sub_exec)
    routed_tasks = [
        t
        for t in compiled_wf.get("tasks") or []
        if t.get("taskType") in {"CALL_MCP_TOOL", "SUB_WORKFLOW", "SIMPLE"}
    ]
    for t in routed_tasks:
        # Reseed dedup: Conductor's executed task list may include retried
        # rows; we want at least one COMPLETED per (taskType, refName).
        pass

    # Each refName must have a COMPLETED instance.
    by_ref: dict[str, set[str]] = {}
    for t in compiled_wf.get("tasks") or []:
        ref = str(t.get("referenceTaskName"))
        if t.get("taskType") in {"CALL_MCP_TOOL", "SUB_WORKFLOW", "SIMPLE"}:
            by_ref.setdefault(ref, set()).add(str(t.get("status")))

    for ref, statuses in by_ref.items():
        assert "COMPLETED" in statuses, (
            f"task ref {ref!r} must have a COMPLETED instance; saw statuses={statuses!r}"
        )
