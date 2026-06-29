#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""PAC end-to-end proof: PLAN_EXECUTE routes by toolType.

Sends a single typed Plan that mixes THREE tool types so the compiled
WorkflowDef proves PAC dispatches each one correctly:

  - ``math_add``         — MCP tool (mcp-testkit) → CALL_MCP_TOOL
  - ``string_uppercase`` — MCP tool (mcp-testkit) → CALL_MCP_TOOL
  - ``mini_agent``       — agent_tool             → SUB_WORKFLOW
  - ``stitch``           — Python worker          → SIMPLE

The fan-out step runs all three in parallel (FORK_JOIN), then the synthesizer
step (SIMPLE worker) folds the three results into one deterministic string.

Validation is algorithmic — no LLM judging. mcp-testkit returns fixed values
(``2 + 40 = 42``, ``"hello" → "HELLO"``); the agent_tool sub-workflow runs
``mini_agent`` which is instructed to return one specific token. The test
asserts the synthesizer output contains all three.

Setup:

    # 1. Start mcp-testkit:
    uv run mcp-testkit --transport http --port 3001

    # 2. (Re)start agentspan server with the new PAC build:
    kill <pid-of-running-agentspan>
    cd server && ./gradlew bootRun

    # 3. Run this script:
    cd sdk/python && uv run python examples/107_pac_mcp_proof.py
"""

from __future__ import annotations

import json
import os
import time

import requests
from settings import settings

from conductor.ai.agents import Agent, AgentRuntime, plan_execute, tool
from conductor.ai.agents.plans import Op, Plan, Step
from conductor.ai.agents.tool import ToolDef, agent_tool

# ── Endpoints ─────────────────────────────────────────────────────────

AGENTSPAN_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
# Conductor REST runs alongside agentspan; we'll read the compiled
# WorkflowDef directly off Conductor to *prove* PAC emitted the right
# task types (not just trust the SDK's view of execution.status).
CONDUCTOR_BASE = AGENTSPAN_URL.replace("/api", "")
MCP_URL = "http://localhost:3001/mcp"


# ── Tool definitions ──────────────────────────────────────────────────


def mcp_static_tool(name: str, description: str, input_schema: dict) -> ToolDef:
    """Declare a *named* MCP tool statically so it can be referenced from
    a typed Plan. ``mcp_tool()`` in the SDK is a discovery wrapper (one
    ToolDef per server); for Plan ops we need one ToolDef per remote
    tool so PAC's name→ToolConfig lookup routes each op to its own
    CALL_MCP_TOOL with the matching ``method`` field.
    """
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="mcp",
        config={"server_url": MCP_URL},
    )


math_add = mcp_static_tool(
    name="math_add",
    description="Add two numbers via the mcp-testkit math_add tool.",
    input_schema={
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
)

string_uppercase = mcp_static_tool(
    name="string_uppercase",
    description="Uppercase a string via the mcp-testkit string_uppercase tool.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)


# Sub-agent wrapped as agent_tool → PAC compiles op to SUB_WORKFLOW
mini_agent = Agent(
    name="mini_agent",
    model=settings.llm_model,
    instructions=(
        "Reply with EXACTLY the single token 'AGENT_OK' and nothing else. "
        "No punctuation, no whitespace, no explanation."
    ),
    max_turns=2,
    max_tokens=32,  # OpenAI Responses API minimum is 16
)


# Deterministic synthesizer (Python worker) → SIMPLE
@tool
def stitch(math_result: object, upper_result: object, agent_result: object) -> str:
    """Stitch the three branch outputs into one deterministic string.

    Args are typed ``object`` because Conductor passes the MCP parsed payload
    as whatever the remote tool returned (number for math, string for
    uppercase). Coerce to str so the assertions downstream can substring-match.
    """
    return f"math={math_result!s}|upper={upper_result!s}|agent={agent_result!s}"


# ── PAC harness ──────────────────────────────────────────────────────

harness = plan_execute(
    name="pac_mcp_proof",
    tools=[math_add, string_uppercase, agent_tool(mini_agent), stitch],
    planner_instructions="",  # typed Plan injected; planner output discarded
    model=settings.llm_model,
)


# ── The typed Plan ────────────────────────────────────────────────────
#
# This is the entire conductor topology, declared in 25 lines:
#
#   FORK_JOIN
#     ├── CALL_MCP_TOOL  math_add(a=2, b=40)
#     ├── CALL_MCP_TOOL  string_uppercase(text="hello")
#     └── SUB_WORKFLOW   mini_agent_agent_wf("Return AGENT_OK")
#   JOIN
#     │
#   SIMPLE  stitch(math_result, upper_result, agent_result)
#
# No Python orchestration — PAC compiles this to FORK_JOIN_DYNAMIC etc.

plan = Plan(
    steps=[
        Step(
            id="fanout",
            parallel=True,
            operations=[
                Op("math_add", args={"a": 2, "b": 40}),
                Op("string_uppercase", args={"text": "hello"}),
                Op("mini_agent", args={"request": "Return AGENT_OK"}),
            ],
        ),
        Step(
            id="synthesize",
            depends_on=["fanout"],
            operations=[
                Op(
                    "stitch",
                    args={
                        # CALL_MCP_TOOL output shape (Conductor system task):
                        #   { content: [ { type, text, parsed: { result: ... } } ], isError }
                        # The MCP server wraps tool returns in MCP content
                        # blocks; ``parsed.result`` is the typed payload.
                        "math_result": "${s_fanout_0.output.content[0].parsed.result}",
                        "upper_result": "${s_fanout_1.output.content[0].parsed.result}",
                        # SUB_WORKFLOW carries the agent's final answer at
                        # output.result (a plain string for stateless agents).
                        "agent_result": "${s_fanout_2.output.result}",
                    },
                ),
            ],
        ),
    ],
)


# ── Algorithmic verification ─────────────────────────────────────────


def fetch_workflow(execution_id: str) -> dict:
    r = requests.get(
        f"{CONDUCTOR_BASE}/api/workflow/{execution_id}",
        params={"includeTasks": "true"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def find_compiled_workflow_def(parent_id: str) -> tuple[str, dict]:
    """Walk parent + sub-workflows to find PAC's compiled WorkflowDef.

    PAC emits its output into a sub-workflow that the harness invokes via
    SUB_WORKFLOW. We follow the chain and return ``(workflowName,
    workflowDef-as-fetched-from-Conductor-metadata)``.
    """
    seen: set[str] = set()
    pending = [parent_id]
    while pending:
        wf_id = pending.pop()
        if wf_id in seen:
            continue
        seen.add(wf_id)
        wf = fetch_workflow(wf_id)
        for t in wf.get("tasks", []):
            if t.get("taskType") == "PLAN_AND_COMPILE":
                out = t.get("outputData") or {}
                wd = out.get("workflowDef")
                if wd:
                    # Read the WorkflowDef out of PAC's task output directly.
                    # The /metadata/workflow/{name} endpoint returns only the
                    # placeholder agentspan registered up-front; PAC compiles
                    # a fresh def per execution and emits it here.
                    return out.get("workflowName", "<unknown>"), wd
            sub = t.get("subWorkflowId")
            if sub:
                pending.append(sub)
    raise RuntimeError("PLAN_AND_COMPILE task not found in workflow tree")


def collect_task_types(wf_def: dict) -> list[tuple[str, str]]:
    """Recursively collect (type, name) tuples from a WorkflowDef tree."""
    out: list[tuple[str, str]] = []

    def walk(tasks: list[dict]) -> None:
        for t in tasks:
            out.append((str(t.get("type")), str(t.get("name"))))
            tt = t.get("type")
            if tt == "FORK_JOIN":
                for branch in t.get("forkTasks") or []:
                    walk(branch)
            elif tt == "SWITCH":
                for branch in (t.get("decisionCases") or {}).values():
                    walk(branch)
                walk(t.get("defaultCase") or [])

    walk(wf_def.get("tasks") or [])
    return out


def main() -> int:
    print("=" * 70)
    print("  PAC end-to-end proof — PLAN_EXECUTE with toolType routing")
    print("=" * 70)
    print(f"  agentspan: {AGENTSPAN_URL}")
    print(f"  conductor: {CONDUCTOR_BASE}")
    print(f"  mcp:       {MCP_URL}")
    print()
    print("  Plan:")
    print("    FORK_JOIN")
    print("      ├── CALL_MCP_TOOL  math_add(a=2, b=40)       → expect '42.0'")
    print("      ├── CALL_MCP_TOOL  string_uppercase('hello') → expect 'HELLO'")
    print("      └── SUB_WORKFLOW   mini_agent                → expect 'AGENT_OK'")
    print("    JOIN → SIMPLE stitch")
    print()

    with AgentRuntime() as rt:
        t0 = time.time()
        result = rt.run(harness, "(typed Plan injected)", plan=plan)
        elapsed = time.time() - t0
        print(f"  execution_id: {result.execution_id}")
        print(f"  status:       {result.status}")
        print(f"  elapsed:      {elapsed:.1f}s")
        print(f"  output:       {result.output!r}")

    # ── Proof 1: compiled WorkflowDef shape ──────────────────────────
    print()
    print("─" * 70)
    print("  PROOF 1: PAC routed each tool to the right Conductor task type")
    print("─" * 70)
    wf_name, wf_def = find_compiled_workflow_def(result.execution_id)
    print(f"  compiled workflow name: {wf_name}")
    types = collect_task_types(wf_def)
    print("  task type → name (depth-first walk of compiled WorkflowDef):")
    for tt, nm in types:
        marker = ""
        if tt == "CALL_MCP_TOOL":
            marker = "  ← mcp toolType"
        elif tt == "SUB_WORKFLOW":
            marker = "  ← agent_tool toolType"
        elif tt == "SIMPLE" and nm == "stitch":
            marker = "  ← worker toolType"
        print(f"    {tt:18s}  {nm}{marker}")

    mcp_count = sum(1 for t, _ in types if t == "CALL_MCP_TOOL")
    sub_count = sum(1 for t, _ in types if t == "SUB_WORKFLOW")
    simple_stitch = any(t == "SIMPLE" and n == "stitch" for t, n in types)
    has_fork_join = any(t == "FORK_JOIN" for t, _ in types)

    assert mcp_count == 2, f"expected 2 CALL_MCP_TOOL tasks, got {mcp_count}"
    assert sub_count == 1, f"expected 1 SUB_WORKFLOW task, got {sub_count}"
    assert simple_stitch, "expected one SIMPLE task named 'stitch'"
    assert has_fork_join, "fanout step must compile to a FORK_JOIN"
    print()
    print("  ✓ 2 × CALL_MCP_TOOL    (mcp toolType routed)")
    print("  ✓ 1 × SUB_WORKFLOW     (agent_tool toolType routed)")
    print("  ✓ 1 × SIMPLE (stitch)  (worker toolType routed)")
    print("  ✓ FORK_JOIN wraps the 3 parallel branches")

    # ── Proof 2: deterministic execution output ──────────────────────
    print()
    print("─" * 70)
    print("  PROOF 2: deterministic algorithmic output (no LLM judging)")
    print("─" * 70)
    output_str = str(result.output)
    print(f"  final output: {output_str!r}")
    # mcp-testkit's math_add(2, 40) returns "42.0"; string_uppercase("hello")
    # returns "HELLO". The sub-agent is prompt-locked to return AGENT_OK.
    assert "math=42.0" in output_str or "math=42" in output_str, (
        f"math_add(2,40) must produce 42 in output; got: {output_str!r}"
    )
    assert "upper=HELLO" in output_str, (
        f"string_uppercase('hello') must produce HELLO; got: {output_str!r}"
    )
    assert "agent=AGENT_OK" in output_str, f"mini_agent must return AGENT_OK; got: {output_str!r}"
    print("  ✓ math=42(.0)        (MCP math_add executed, deterministic output)")
    print("  ✓ upper=HELLO        (MCP string_uppercase executed)")
    print("  ✓ agent=AGENT_OK     (agent_tool sub-workflow executed)")

    # ── Proof 3: print the compiled WorkflowDef as visible artifact ──
    print()
    print("─" * 70)
    print("  PROOF 3: compiled WorkflowDef (Conductor metadata)")
    print("─" * 70)
    print(json.dumps({"name": wf_def["name"], "tasks": wf_def.get("tasks")}, indent=2)[:3500])
    print("  ... (truncated)")
    print()
    print("=" * 70)
    print("  ALL CHECKS PASSED ✓")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
