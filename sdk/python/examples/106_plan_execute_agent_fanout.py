#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""PLAN_EXECUTE with agent fan-out — Conductor-native, fully declarative.

Demonstrates the fix that makes ``Strategy.PLAN_EXECUTE`` route plan ops by
the underlying tool's ``toolType``:

  - A plan op whose tool has ``toolType=agent_tool`` compiles to a Conductor
    ``SUB_WORKFLOW`` (the child agent runs as its own durable workflow).
  - A plan step with ``parallel=True`` compiles to a ``FORK_JOIN`` over those
    branches. Per-branch retry/optional flow through.
  - Sequential steps run after the join completes.

Before the fix, agent_tool ops compiled to ``SIMPLE`` tasks with no worker
on the other end — they polled forever. ``scatter_gather`` was the only way
to fan out to sub-agents; that route required an LLM coordinator to issue
N tool calls at runtime. PLAN_EXECUTE now expresses the same fan-out as a
typed Python Plan, no LLM-in-the-loop.

This example bypasses the planner LLM entirely by passing ``plan=`` to
``runtime.run``. The planner stub still gets dispatched (PAC's contract),
but its output is discarded — the typed Plan you build below IS what gets
compiled to a WorkflowDef.

Pipeline:

    Plan(parallel: [worker_a, worker_b, worker_c])
        ↓ PAC compiles
    FORK_JOIN
      ├── SUB_WORKFLOW  worker_a_agent_wf   "Summarise topic A"
      ├── SUB_WORKFLOW  worker_b_agent_wf   "Summarise topic B"
      └── SUB_WORKFLOW  worker_c_agent_wf   "Summarise topic C"
    JOIN
        ↓
    SIMPLE  echo_assemble  (sequential synthesizer)

Run:
    python 106_plan_execute_agent_fanout.py

Requires:
    - Agentspan server running (AGENTSPAN_SERVER_URL)
    - OPENAI_API_KEY (planner LLM gets called even when ``plan=`` is injected
      — its output is discarded but the call has to land somewhere)
"""

from __future__ import annotations

from settings import settings

from conductor.ai.agents import Agent, AgentRuntime, plan_execute, tool
from conductor.ai.agents.plans import Op, Plan, Step
from conductor.ai.agents.tool import agent_tool

# ── Deterministic worker (no LLM) — used as the sequential synthesizer ─


@tool
def echo_assemble(parts: str) -> str:
    """Join input parts with newlines and prefix with a header.

    Args:
        parts: A pipe-separated string of pieces to assemble.
    """
    pieces = [p.strip() for p in (parts or "").split("|") if p.strip()]
    return "=== Assembled report ===\n" + "\n\n".join(pieces)


# ── Worker agent (LLM-driven) — wrapped as an agent_tool ───────────────

subtask_worker = Agent(
    name="subtask_worker",
    model=settings.llm_model,
    instructions=(
        "You are a brief researcher. You will be given ONE short topic. "
        "Return exactly two sentences: a definition followed by a notable "
        "use case. No markdown, no headings, no preamble."
    ),
    max_turns=3,
    max_tokens=300,
)


# ── PAC harness ────────────────────────────────────────────────────────
#
# ``plan_execute`` builds the planner+harness. The planner instructions are
# empty here because we inject a typed Plan at run time — the planner
# stub gets called but its output is discarded by PAC's plan injection.
# ``tools=[agent_tool(...), echo_assemble]`` is the canonical plan-executable
# set; every ``op.tool`` in the typed Plan below is validated against it.
harness = plan_execute(
    name="agent_fanout_demo",
    tools=[agent_tool(subtask_worker), echo_assemble],
    planner_instructions="",  # typed Plan is injected; planner output is discarded
    model=settings.llm_model,
)


# ── The typed Plan — Conductor fan-out made explicit in 20 lines ──────

TOPICS = ["epigenetics", "vector databases", "kalman filters"]

plan = Plan(
    steps=[
        # Fan out: each branch invokes ``subtask_worker`` (agent_tool →
        # SUB_WORKFLOW under the hood). ``parallel=True`` is what makes
        # PAC emit a FORK_JOIN; N is the number of operations in this
        # step. No LLM coordinator, no Python loop dispatching subworkflows.
        Step(
            id="fanout",
            parallel=True,
            operations=[
                Op("subtask_worker", args={"request": f"Topic: {topic}"}) for topic in TOPICS
            ],
        ),
        # Sequential synthesizer. The aggregator's output (a list of the
        # parallel branches' results) is piped into echo_assemble. PAC's
        # parallel-agg INLINE wires this up for us — ``echo_assemble`` just
        # reads a pipe-separated string from the workflow's outputParameters.
        Step(
            id="assemble",
            depends_on=["fanout"],
            operations=[
                Op(
                    "echo_assemble",
                    # parallel aggregator returns a JSON array; coerce to the
                    # pipe-separated string echo_assemble expects.
                    args={"parts": "${parallel_agg_fanout_5.output.result}"},
                ),
            ],
        ),
    ],
)


def main() -> int:
    print("=" * 70)
    print("  PLAN_EXECUTE with agent fan-out")
    print("  Plan compiles to:")
    print("    FORK_JOIN")
    for i, t in enumerate(TOPICS):
        print(f"      ├── SUB_WORKFLOW  subtask_worker_agent_wf   ({t})")
    print("    JOIN → SIMPLE echo_assemble")
    print("=" * 70)

    with AgentRuntime() as rt:
        result = rt.run(harness, "(unused; typed Plan injected)", plan=plan)
        print(f"\nExecution: {result.execution_id}")
        print(f"Status:    {result.status}")
        result.print_result()
    return 0 if result.status in ("COMPLETED", "") else 1


if __name__ == "__main__":
    raise SystemExit(main())
