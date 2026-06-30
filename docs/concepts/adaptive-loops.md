---
title: Adaptive Loops
description: Durable iterative agents — each iteration is a Conductor workflow. Iterate until correct, observe every step, and survive crashes mid-loop.
---

# Adaptive Loops

**Any framework can loop. Only Agentspan makes each iteration a durable, observable workflow.**

A Python `while` loop dies with your process. An Agentspan adaptive loop is a sequence of Conductor workflow executions — each iteration crash-safe, fully logged, and visible in the execution UI. The loop continues from the current iteration on reconnect, not from scratch.

!!! tip "The core insight"
    Combine **Plan-Execute** for deterministic per-iteration execution with an **adaptive outer loop** that steers based on verified results. The LLM adapts *what* to try next; Conductor handles *how* each attempt runs — with parallelism, retry, validation, and crash recovery built in.

---

## Why durable loops matter

| | Plain while loop | Agentspan adaptive loop |
|---|---|---|
| Process crash mid-loop | Entire loop lost | Resume at current iteration |
| Observability | No record | Every iteration logged in UI |
| Per-iteration execution | LLM-driven, non-deterministic | Plan-Execute: deterministic |
| Parallelism within iteration | Manual threading | FORK_JOIN — free, crash-safe |
| Loop termination | Hope the LLM stops | Server-enforced DO_WHILE condition |
| Replay a specific iteration | Impossible | Full replay — plan is a value |

---

## Pattern 1 — User-code replan loop

The simplest shape: wrap `runtime.run()` in your own loop, inspect the output, build the next plan.

```python
from conductor.ai.agents import plan_execute, Plan, Step, Op, Validation

harness = plan_execute(
    name="solver",
    tools=[propose_solution, run_tests, check_constraints],
    planner_instructions="Propose a solution. You will be told exactly what failed.",
)

plan = build_initial_plan(prompt)

for iteration in range(max_iterations):
    result = runtime.run(harness, prompt, plan=plan)

    verdict = evaluate(result)          # deterministic verifier — no LLM
    if verdict.passed:
        break

    # Thread failures into next iteration's generate instructions
    plan = build_next_plan(prompt, verdict.failures)
```

**What makes this different from a plain while loop:**

- Each `runtime.run()` is a full Conductor workflow — crash mid-iteration → resume at the current step.
- The inner execution is deterministic (Plan-Execute). Only the outer replanning call touches the LLM.
- Every iteration has its own execution record in the UI.

### Adaptive goal-seeking (example 110)

The pattern generalises to any LLM-generator + deterministic-verifier pair:

```python
for iteration in range(max_iterations):
    # K parallel proposers — deterministic FORK_JOIN, not LLM fan-out
    plan = Plan(steps=[
        Step("propose", parallel=True, operations=[
            Op("propose_solution", generate=Generate(
                instructions=f"Candidate {i}. Previous failures: {failures}",
                output_schema='{"solution": "..."}',
            ))
            for i in range(K)
        ]),
        Step("verify", depends_on=["propose"], operations=[
            Op("run_tests", args={"candidates": Ref("propose")}),
        ]),
    ])

    result = runtime.run(harness, prompt, plan=plan)
    verdict = parse_verdict(result)

    if any(c.passed for c in verdict.candidates):
        break

    # Each candidate's exact failure modes feed into the next round
    failures = [c.failure_detail for c in verdict.candidates]
```

This converges by *fixing what the previous attempt got wrong*, not retrying the same prompt with a different seed.

---

## Pattern 2 — DO_WHILE inside a single workflow

For loops that should be **one execution** (one workflow ID, all iterations visible as a unit), build the loop inside the Conductor workflow using a `DO_WHILE` task. The entire loop — every iteration — appears under one execution ID in the UI.

```
Workflow (single ID)
└── DO_WHILE
    ├── planner_llm__1    ← LLM_CHAT_COMPLETE, iteration 1
    ├── plan_and_compile__1
    ├── sub_workflow__1   ← the compiled plan executes here
    ├── reviewer_llm__1
    ├── planner_llm__2    ← iteration 2 (same workflow)
    ├── plan_and_compile__2
    ├── sub_workflow__2
    └── ...
```

Iterations share `workflow.variables` — state accumulates across iterations without leaving the workflow. The DO_WHILE condition is a JavaScript expression evaluated by Conductor's engine: same input → same branch, every time.

### AML/SAR investigation (example 113)

A compliance investigation loop: the planner picks the next-best evidence source per iteration; the loop terminates when the case is dispositioned.

```python
# High-level structure (see examples/113_aml_sar_investigation_loop.py for full code)
aml_workflow = build_do_while_workflow(
    name="sar_investigation",
    body=[
        planner_task,           # LLM picks next evidence source
        pac_compile_task,       # PAC compiles the evidence-gathering plan
        sub_workflow_task,      # deterministic execution
        reviewer_task,          # LLM decides: need_more_evidence | disposition
        update_state_task,      # SET_VARIABLE — accumulates findings
    ],
    condition="$.reviewer_output.decision != 'need_more_evidence'",
)
```

### Portfolio rebalancing (example 114)

Multi-constraint convergence with wash-sale / concentration / drift checks. Each iteration refines the trade list; the loop exits when all constraints pass.

---

## When to use each pattern

| | User-code loop (Pattern 1) | DO_WHILE workflow (Pattern 2) |
|---|---|---|
| Simplicity | Simpler to write | Requires workflow construction |
| Observability | Separate execution per iteration | Single execution ID, all iterations in one view |
| State between iterations | Python variables | `workflow.variables` in Conductor |
| Crash recovery | Resume at current iteration | Resume at current task within iteration |
| Loop condition | Python `if` | JS expression in Conductor |
| Best for | Exploration, prototyping | Production pipelines, compliance, finance |

---

## Upcoming: `Strategy.PLAN_EXECUTE_REPLAN`

The replan pattern will become a first-class SDK strategy — `Strategy.PLAN_EXECUTE_REPLAN` — eliminating the need to write the outer loop manually. Declaration will look like:

```python
# Coming soon
harness = Agent(
    name="solver",
    strategy=Strategy.PLAN_EXECUTE_REPLAN,
    planner=planner,
    fallback=fallback,
    tools=[...],
    max_iterations=10,
    stop_condition="$.verdict.passed == true",
)
```

The server will manage the DO_WHILE loop, making the entire multi-iteration run a single observable workflow with one execution ID.

---

## Examples

- `examples/118_adaptive_loop_showcase.py` — **start here**: single-execution travel planner that iterates until budget constraints pass; shows the agent-tool-loop pattern in ~150 lines (`python 118_adaptive_loop_showcase.py "Tokyo"`)
- `examples/119_research_report_pae_replan.py` — **PAE-replan**: research report using DO_WHILE + PAC; planner writes only failing sections each iteration; one execution ID, FORK_JOIN parallel writes (`python 119_research_report_pae_replan.py "AI agents"`)
- `examples/109_plan_execute_replan.py` — basic replan with rule-based decider
- `examples/110_plan_execute_replan_solve.py` — K parallel proposers + deterministic verifier, converges by fixing failures
- `examples/111_plan_execute_replan_binsearch.py` — binary search loop (~log₂ N iterations to converge)
- `examples/112_dowhile_loop_inside_workflow.py` — DO_WHILE inside a single Conductor workflow
- `examples/113_aml_sar_investigation_loop.py` — AML/SAR investigation with PAC sub-workflows per iteration
- `examples/114_portfolio_rebalance_loop.py` — portfolio rebalancing with multi-constraint convergence
