---
title: Plan-Execute Strategy
description: PLAN_EXECUTE compiles LLM-generated (or static) plans into deterministic Conductor sub-workflows — the planner reasons, the executor runs.
---

# Plan-Execute Strategy

`Strategy.PLAN_EXECUTE` (also called PAE; the server-side compiler is PAC, "PLAN_AND_COMPILE") splits a task into two phases:

1. **Plan** — a planner agent emits a JSON DAG of operations.
2. **Execute** — the server compiles that JSON into a Conductor sub-workflow and runs it deterministically.

The LLM is only invoked where it adds value (planning, per-op content generation). Orchestration, retries, parallelism, and validation are pure Conductor primitives — no token cost, no nondeterminism.

## When to use it

PLAN_EXECUTE wins when the work has **fixed structure but variable content**:

- Generate a research report (3 sections, parallel writes, then assemble + validate)
- Process a batch of records with conditional branches
- Multi-stage refactor where each stage is the same shape but the inputs differ
- Anywhere you'd otherwise hand-write 20 turns of LLM tool-calling and hope it doesn't loop

If you need fully agentic exploration with no fixed shape, use `Strategy.HANDOFF` instead. If you have a fully fixed pipeline, use `Strategy.SEQUENTIAL`. PLAN_EXECUTE is the middle ground.

## The shape

```python
from agentspan.agents import Strategy, Agent, plan_execute

# One-call construction (recommended):
harness = plan_execute(
    name="report_generator",
    tools=[create_directory, write_file, assemble_files, check_word_count],
    planner_instructions="Plan a research report on the user's topic. Use 3 sections, then assemble.",
    fallback_instructions="The deterministic plan failed — recover agentically.",
)

# Or assemble manually if you need every knob:
planner = Agent(name="planner", instructions=PLANNER_INSTRUCTIONS, model=...)
fallback = Agent(name="fb", instructions=FALLBACK_INSTRUCTIONS, tools=[...], model=...)
harness = Agent(
    name="report_generator",
    strategy=Strategy.PLAN_EXECUTE,
    planner=planner,
    fallback=fallback,
    tools=[...],         # canonical plan-executable set; PAC validates against this
    fallback_max_turns=5,
)
```

The **planner**, **fallback**, and **tools** slots are the three first-class fields. `agents=[...]` is **not** valid for PLAN_EXECUTE — set the named slots.

## Plan schema

The server auto-appends a `## Plan schema` block to the planner's user prompt (along with `## Available tools` derived from `harness.tools`). Your `planner_instructions` only needs to cover **domain-level guidance** — what to plan, not how to format JSON.

The schema PAC consumes:

```json
{
  "steps": [
    {
      "id": "<unique step id>",
      "depends_on": ["<other step id>"],
      "parallel": false,
      "operations": [
        {"tool": "<tool>", "args": {<literal arg map>}},
        {"tool": "<tool>", "generate": {
          "instructions": "<what the LLM should produce>",
          "output_schema": "<JSON shape that becomes the tool's args>",
          "max_tokens": 4096
        }}
      ]
    }
  ],
  "validation": [
    {"tool": "<validator>", "args": {...},
     "success_condition": "$.passed === true"}
  ],
  "on_success": [{"tool": "<tool>", "args": {...}}],
  "on_failure": [{"tool": "<tool>", "args": {...}}]
}
```

**Key concepts:**

- **`args` vs `generate`** — `args` runs the tool with literal values you decide at plan time. `generate` defers arg construction to a per-op LLM call at run time.
- **`depends_on`** — cross-step concurrency. A step starts when *all* listed deps complete. Defaults to the previous step.
- **`parallel`** — when true, the step's own `operations` run concurrently (FORK_JOIN). Without it, operations run in order within the step.
- **`success_condition`** — JS expression evaluated against the validator's output (`$` = parsed output map). Returns truthy on pass.
- **`on_success` / `on_failure`** — tools to run after validation. Optional.

## Typed plans (no JSON soup)

For static plans (or plans you build programmatically), import the typed builders:

```python
from agentspan.agents import Plan, Step, Op, Generate, Validation, Action

plan = Plan(
    steps=[
        Step("setup", operations=[Op("create_directory", args={"path": "out"})]),
        Step(
            "write",
            depends_on=["setup"],
            parallel=True,
            operations=[
                Op("write_file", generate=Generate(
                    instructions="Write the introduction.",
                    output_schema='{"path": "out/intro.md", "content": "..."}',
                )),
            ],
        ),
    ],
    validation=[
        Validation("check_word_count", args={"path": "out/intro.md", "min_words": 200}),
    ],
)
```

IDE autocomplete, Pylance type-checks, no escaping nightmares.

## Static plans — skip the planner LLM

Pass a `Plan` (or a raw dict in the same shape) to `runtime.run` and PAC uses it directly:

```python
result = runtime.run(harness, "anything", plan=plan, cwd=work_dir)
```

The planner LLM still runs (the workflow shape is fixed at compile time) but its output is discarded — PAC's `extract_json` reads `workflow.input.static_plan` as Case 0, which wins over planner output. Use this for:

- Tests (deterministic plan, no LLM nondeterminism)
- Replays of a previously-emitted plan
- Pipelines where planning lives outside the agent (a separate service or a code path that builds the `Plan` object)

## Tool guardrails propagate

`@tool(guardrails=[...])` works inside PLAN_EXECUTE the same way it works in the LLM-loop:

```python
no_pii = RegexGuardrail(patterns=[r"\b\d{16}\b"], on_fail=OnFail.RAISE, ...)

@tool(guardrails=[no_pii])
def send_email(to: str, body: str) -> str: ...
```

PAC wraps every emitted SIMPLE for `send_email` in a guardrail SWITCH gate. The bare SIMPLE only runs from the gate's `pass` branch. If the guardrail trips:

- `on_fail=raise` — TERMINATE the dynamic plan; harness's `fallback` agent recovers
- `on_fail=retry` / `fix` / `human` — collapse to TERMINATE in plan mode; same fallback path. (See `OnFail` docstring for full semantics — there's no LLM loop in plan mode to feed retry feedback into; the fallback IS the retry loop.)

The compiler emits **only the SWITCH cases that are reachable** for the configured `on_fail`. An `on_fail=raise` guardrail produces one `raise` case, not four dead branches.

## Fallback — the recovery agent

Configure `fallback=<Agent>` on the harness for adaptive recovery when:

- The planner emits a malformed plan (PAC validation fails)
- A guardrail trips on a deterministic step
- A plan step itself fails at run time

The fallback runs as a normal LLM-loop agent with the harness's `tools`. It receives the original prompt + the failure context (planner output, error message). `fallback_max_turns` caps its turn count during recovery.

Without a fallback, any failure terminates the workflow. Acceptable for fail-loud pipelines; surprising otherwise — the SDK warns at compile time when guardrails with `on_fail≠raise` are configured but no fallback exists.

## What PAC actually emits

For a plan with N parallel steps + 1 validator, the compiled WorkflowDef looks roughly like:

```
SET_VARIABLE      _ctx_init
FORK_JOIN         (per-step branches)
  LLM_CHAT_COMPLETE  (per generate op)
  INLINE             (parse LLM JSON output)
  SWITCH             (parse-error gate)
  SIMPLE             (the tool call)
JOIN
INLINE            (aggregate parallel branch results — only if downstream reads it)
SIMPLE            (validator)
INLINE            (val_eval — emits "passed"/"failed")
SWITCH vsw        ("passed" → on_success, default → TERMINATE/on_failure)
```

The `## Available tools` block in the planner prompt and PAC's validator share the same source: `harness.tools`. A planner can't emit a tool name that PAC will reject (and PAC will reject anything not in the harness's set — closes the hallucinated-tool-name bug).

## Common patterns

### Research report (LLM-driven planning)

```python
harness = plan_execute(
    name="report",
    tools=[create_directory, write_file, assemble_files, check_word_count],
    planner_instructions="Plan a research report on the user's topic. Use 3 sections.",
    fallback_instructions="Fix what the deterministic plan couldn't.",
)
result = runtime.run(harness, "AI agents in 2025")
```

### Static pipeline (no planner reasoning needed)

```python
harness = plan_execute(name="ingest", tools=[fetch, transform, store])
plan = Plan(steps=[
    Step("fetch", operations=[Op("fetch", args={"url": url})]),
    Step("transform", depends_on=["fetch"], operations=[Op("transform", args={"path": "raw.json"})]),
    Step("store", depends_on=["transform"], operations=[Op("store", args={"key": "result"})]),
])
result = runtime.run(harness, "ingest job", plan=plan)
```

### Parallel work + validation

```python
plan = Plan(
    steps=[
        Step("setup", operations=[Op("create_directory", args={"path": "out"})]),
        Step("write_all", depends_on=["setup"], parallel=True, operations=[
            Op("write_file", generate=Generate(
                instructions=f"Write section {i}.",
                output_schema=f'{{"path": "out/{i}.md", "content": "..."}}',
            ))
            for i in range(5)
        ]),
        Step("assemble", depends_on=["write_all"], operations=[
            Op("assemble_files", args={"output_path": "report.md", "input_paths": "..."})
        ]),
    ],
    validation=[Validation("check_word_count", args={"path": "report.md", "min_words": 1000})],
)
```

## Knobs reference

| Field | Purpose |
|---|---|
| `planner=` | Required. The agent that emits the JSON plan. |
| `fallback=` | Optional. Agentic recovery when a plan can't compile/exec. |
| `tools=` | Required. Plan-executable tool set. PAC validates `op.tool` names against this list and propagates each tool's guardrails. |
| `fallback_max_turns=` | Caps the fallback agent's turn count during recovery. |
| `plan_source=` | Compile-time deterministic plan via a tool call. (Use `plan=` at run time instead — same effect, simpler.) |

| Run-time kwarg | Purpose |
|---|---|
| `plan=` | Skip the planner LLM's output; use this `Plan`/dict directly. |
| `cwd=` | Working directory for filesystem-bound tools. |

## Examples

- `examples/85_plan_execute_harness.py` — research report with LLM planner + fallback recovery
- `examples/103_plan_and_compile.py` — minimal PAC demo with `args` + `generate` ops + validation
- `examples/104_plan_execute_guardrails.py` — guardrail propagation in plan mode
- `examples/100_issue_fixer_agent.py` — production-shape pipeline with PLAN_EXECUTE coder + agentic fallback

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Workflow FAILED with "uses unknown tool" in PAC error | Planner emitted a tool name not in `harness.tools` | Add the tool, or fix the planner prompt; the auto-injected `## Available tools` block already constrains the planner — check it appears in your prompt |
| Workflow FAILED, no fallback ran | `plan_exec` SUB_WORKFLOW failure not caught | Confirm `harness.fallback` is set; failures route through `exec_route` SWITCH to fallback |
| Guardrail tripped, workflow terminated | No fallback configured for `on_fail=retry/fix/human` | Configure a fallback or set `on_fail=raise` to acknowledge fail-closed semantics |
| Plan compiled but did wrong thing | Planner LLM produced a syntactically-valid but semantically-wrong plan | Improve `planner_instructions`; consider switching to `plan=` static plan for deterministic flows |
