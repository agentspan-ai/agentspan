# Copyright (c) 2025 Agentspan
# Licensed under the MIT License.

"""108 — Plan-Execute with cross-step output piping via ``Ref``.

The ``Ref("step_id")`` helper wires the **whole output** of an upstream
step into a downstream step's args. No JSON path, no field selection,
no internal task-ref naming to memorise — one line of Python and the
runtime substitutes the value at execution time.

The pattern this enables:

    Step("fetch", operations=[Op("fetch_data", args={"url": URL})])
    Step("summarize", depends_on=["fetch"], operations=[
        Op("summarize", args={"document": Ref("fetch")}),
    ])

This example runs a three-step pipeline:

    produce → enrich → report

``produce`` emits a record dict, ``enrich`` adds a derived field via
``Ref("produce")``, and ``report`` reads ``Ref("enrich")`` to format a
final summary. The plan is fully deterministic — no planner LLM
required — because we pass ``plan=`` directly to ``runtime.run``.

What to look for in the output:
  * ``enrich`` receives the whole ``produce`` dict, not the literal
    ``{"$ref": "produce"}`` marker.
  * ``report`` reads ``enrich``'s output and ``produce``'s output
    independently (two Refs in the same args map).

Requirements:
  - AGENTSPAN_SERVER_URL=http://localhost:6767/api (default)
  - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini (default)
"""

from __future__ import annotations

import os

from conductor.ai.agents import AgentRuntime, Op, Plan, Ref, Step, plan_execute, tool


@tool
def produce(record_id: str) -> dict:
    """Emit a structured record. Step A."""
    return {
        "record_id": record_id,
        "value": 42,
        "tags": ["alpha", "beta"],
    }


@tool
def enrich(record: dict) -> dict:
    """Append a derived field. Step B reads Step A via ``Ref('produce')``."""
    return {
        **record,
        "value_squared": record["value"] ** 2,
    }


@tool
def report(record: dict, enriched: dict) -> dict:
    """Format the final report. Step C reads BOTH upstream steps."""
    return {
        "id": record["record_id"],
        "original_value": record["value"],
        "squared": enriched["value_squared"],
        "tags_joined": ", ".join(record["tags"]),
        "summary": (
            f"record={record['record_id']} value={record['value']} "
            f"squared={enriched['value_squared']} tags={record['tags']}"
        ),
    }


def main() -> None:
    harness = plan_execute(
        name="ref_demo",
        tools=[produce, enrich, report],
        planner_instructions="(planner unused; static plan supplied)",
        model=os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )

    plan = Plan(
        steps=[
            Step("produce", operations=[Op("produce", args={"record_id": "r-001"})]),
            Step(
                "enrich",
                depends_on=["produce"],
                operations=[Op("enrich", args={"record": Ref("produce")})],
            ),
            Step(
                "report",
                depends_on=["produce", "enrich"],
                operations=[
                    Op(
                        "report",
                        args={
                            "record": Ref("produce"),
                            "enriched": Ref("enrich"),
                        },
                    ),
                ],
            ),
        ],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(harness, "demo", plan=plan, timeout=120)
        result.print_result()

        # The harness's final outputParameters don't surface per-step worker
        # results by default — print them explicitly so this example doubles
        # as a proof that `Ref()` actually carried the upstream dicts.
        _show_pipeline_outputs(result.execution_id)


def _show_pipeline_outputs(execution_id: str) -> None:
    """Walk into the plan_exec sub-workflow and dump the three step outputs."""
    import json

    import requests

    base = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    base_url = base.rstrip("/").replace("/api", "")

    parent = requests.get(
        f"{base_url}/api/workflow/{execution_id}?includeTasks=true", timeout=10
    ).json()
    sub_id = None
    for t in parent.get("tasks", []):
        if t.get("referenceTaskName", "").endswith("_plan_exec"):
            sub_id = (t.get("outputData") or {}).get("subWorkflowId")
            break
    if not sub_id:
        return

    sub = requests.get(
        f"{base_url}/api/workflow/{sub_id}?includeTasks=true", timeout=10
    ).json()
    print("\n── pipeline trace (Ref data flow) ────────────────────────")
    for t in sub.get("tasks", []):
        name = t.get("taskDefName")
        if name in ("produce", "enrich", "report"):
            print(f"\n{name}:")
            print(json.dumps(t.get("outputData", {}), indent=2))


if __name__ == "__main__":
    main()
