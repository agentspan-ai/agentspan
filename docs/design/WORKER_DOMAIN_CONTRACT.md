# Worker Domain Contract — RCA, Rule, and Test Guarantee

## TL;DR

Three "worker not polling for tool X" regressions in this branch — all the same shape: **the server schedules a `(task_name, domain)` pair that the SDK never registered a worker for**. The fixes patched specific gaps but didn't establish a contract. This doc names the contract, applies it, and adds a runtime invariant check + property test that catches any future drift before the workflow starts polling.

## The recurring symptom

A workflow has tasks in `SCHEDULED` state with no `pollCount` increment. Inspecting the task shows it carries a `domain` field. No worker is polling that `(taskDefName, domain)` queue.

Three instances on this branch:

| Workflow | What was scheduled with no poller | What was missing |
|---|---|---|
| `b38024fb` | `read_repo_docs` prefill task | The SDK's `_collect_worker_names` walked `agent.tools` only — missed `agent.prefill_tools`. Tools that appeared *only* in `prefill_tools` got scheduled by the server but never registered locally. |
| `0f715217` | `contextbook_read` prefill on `code_planner` | The SDK's `_collect_worker_names` recursed via `agent.agents` only — missed `agent.planner` and `agent.fallback`. PAE harnesses keep sub-agents in named slots, not in `agents`. |
| `4e0d2953` | `read_repo_docs` (non-stateful) on a per-execution domain | Server-side policy: when `runId` is set, *all* SIMPLE tasks go into `taskToDomain`. SDK-side policy: register a worker under a domain only when the tool itself is stateful. The two policies disagree. |

Each fix added one more recursion or path. None of them established the underlying property that every fix was implicitly trying to satisfy.

## The contract

> **For every `(task_name, domain)` pair the server places in `StartWorkflowRequest.taskToDomain`, the SDK MUST have a registered worker on that exact pair before the workflow begins executing.**
>
> Equivalently: server-emitted `taskToDomain` ⊆ SDK-registered `(name, domain)` pairs.

This is referential integrity. It's the single property both sides need to agree on. Every prior bug was a violation of this property.

The contract also implies the symmetric direction (a registered worker with no scheduled task is harmless waste, but registered-without-scheduled isn't a correctness bug — only the other direction is).

## The two policies and why they disagreed

**Server policy** (`AgentService.start`, line 320–325):

```java
if (request.getRunId() != null && !request.getRunId().isEmpty()) {
    Map<String, String> taskToDomain = new HashMap<>();
    for (String taskName : startWorkerNames) {            // every SIMPLE in WorkflowDef
        taskToDomain.put(taskName, request.getRunId());
    }
    collectWorkerToolNames(config, taskToDomain, request.getRunId());  // stateful tools
    ...
}
```

Reasoning (preserved as a comment in the source): "We cannot use `*` because that would also route system tasks like LLM_CHAT_COMPLETE to the domain". The intent was *isolation per execution*: every worker invocation in a stateful run goes to that run's domain so cross-execution interference can't happen.

**SDK policy** (`ToolRegistry.register_tool_workers`):

```python
worker_task(
    task_definition_name=td.name,
    domain=domain if (agent_stateful or td.stateful) else None,
    ...
)
```

Reasoning: only stateful tools have per-execution state, so only they need per-execution worker isolation. Non-stateful tools can be served by any worker — registering them under a per-execution domain just multiplies worker startup cost.

Both are coherent in isolation. Run together they break.

## The fix — pick one policy, apply it on both sides

We standardise on the **SDK's per-tool-stateful policy**. Reasons:

1. Lower worker startup cost — non-stateful tools share a single global worker across executions.
2. Cleaner semantics — "this tool keeps state per execution" maps to "stateful=True" in one place, not implicitly to "anything used in a stateful execution."
3. Matches what every existing example expects — the SDK side is what users build against.

### Concrete change

`AgentService.start` no longer adds *every* SIMPLE task name to `taskToDomain`. It adds only what `collectWorkerToolNames` produces — stateful tools and stateful guardrail tasks. The all-tasks loop is removed:

```java
// before
for (String taskName : startWorkerNames) {
    taskToDomain.put(taskName, request.getRunId());
}
collectWorkerToolNames(config, taskToDomain, request.getRunId());

// after — only stateful tools
collectWorkerToolNames(config, taskToDomain, request.getRunId());
```

This makes the server's contribution to `taskToDomain` exactly the set of stateful tool names from the agent tree, which matches what the SDK registers under the per-run domain.

## The runtime invariant — make violations loud

Adding a contract isn't enough; we need a **failure mode that surfaces violations immediately rather than silently letting tasks sit SCHEDULED**.

Before workflow polling begins (after `_start_via_server` returns and before the watchdog starts), the SDK fetches the server's actual `taskToDomain` for the started execution and asserts:

```
∀ (name, domain) ∈ server.taskToDomain:
    (name, domain) ∈ self._collect_registered_pairs(agent, domain)
```

Any violation raises `WorkerDomainMismatchError` with a descriptive message naming the missing tool, the expected domain, the agent name where it was declared, and the suggested fix (most often: add to `tools=` or set `stateful=False`).

This converts the silent failure mode into a loud one. A regression in any of the four worker-discovery functions (`_collect_worker_names`, `_register_workers`, `_has_worker_tools`, `_collect_registered_pairs`) trips the invariant within seconds of `rt.run` being called — long before the user notices a hung workflow.

## The test — formal proof of catch-coverage

Two layers of test guarantee:

### Layer 1 — property test

Given any agent tree, the SDK-registered `(name, domain)` pairs must be a superset of what `taskToDomain` would carry for that tree. The test reproduces the server's `collectWorkerToolNames` logic (Java) in a Python helper that walks the same agent tree, then compares against `_collect_registered_pairs`.

```python
def assert_worker_contract(agent: Agent, run_id: str | None) -> None:
    expected = compute_server_task_to_domain(agent, run_id)  # mirrors Java logic
    registered = set(rt._collect_registered_pairs(agent, run_id))
    missing = {pair for pair in expected.items() if pair not in registered}
    assert not missing, (
        f"Worker contract violation: server schedules {missing} "
        f"but SDK has no matching registered worker."
    )
```

### Layer 2 — historical regression suite

Each of the three known failure modes (`b38024fb`, `0f715217`, `4e0d2953`) is a parametrised test case:

```python
@pytest.mark.parametrize("name,build_agent", [
    ("b38024fb_prefill_only_tool", _b38024fb),
    ("0f715217_pae_named_slot",    _0f715217),
    ("4e0d2953_non_stateful_in_stateful_run", _4e0d2953),
])
def test_worker_contract_holds(name, build_agent):
    agent, run_id = build_agent()
    assert_worker_contract(agent, run_id)
```

Each `_*` builder constructs the exact agent tree shape that hit the bug. The test passes only when all four worker-discovery code paths are correct.

### Why this is "formal" enough

The catch-coverage proof rests on three observations:

1. **`assert_worker_contract` is a complete invariant** — its premise is the literal contract. If the contract holds, no scheduled task can lack a worker. (Contrapositive: if some task lacks a worker, the contract is violated, the assertion fails.)

2. **The Python helper mirrors the Java `collectWorkerToolNames` source.** It's not an aspirational re-implementation; it computes the same set the server actually uses. We pin them with a cross-language fixture: a small workflow with known stateful + non-stateful tools is run end-to-end, the server's `taskToDomain` from the resulting workflow is read back, and the Python helper's output is asserted equal. Drift between the two is detected immediately.

3. **The historical cases are reproduced exactly.** The three regression builders construct agent trees that hit the prior failures at the SDK-runtime-walk level, not at the workflow level. They don't depend on a server being up. They run in the unit-test suite (~ms) and they fail without their respective fixes.

Together: the property test asserts the contract abstractly, the regression suite asserts it for every known historical failure, and the runtime invariant asserts it for every actual `rt.run` call. The invariant is the strongest layer — even a regression that slips past CI gets caught by the runtime check the next time anyone runs an agent.

## The rule

Going forward, when modifying any of:

- `_collect_worker_names`
- `_register_workers`
- `_has_worker_tools`
- `_collect_registered_pairs`
- `AgentService.collectWorkerToolNames` (server)
- `AgentService.start` (server, the taskToDomain construction)
- `AgentConfig.tools` / `prefill_tools` / `planner` / `fallback` / `agents` traversal in any related helper

…the change MUST run the property test (`uv run pytest tests/unit/test_worker_contract.py`) and the historical regression suite. CI gates this. If a new agent-tree shape (e.g., new strategy with a new sub-agent slot) is introduced, a new regression case MUST be added to the suite at the same time as the implementation, NOT in a follow-up.

The "test-the-contract" gate is the single rule. Any worker-discovery code change without an accompanying contract assertion is a violation of this rule.

## Aftermath of the three fixes

| Bug ID | Fix | Test that would have caught it |
|---|---|---|
| `b38024fb` | Walk `agent.prefill_tools` in `_collect_worker_names` and `_register_workers`. `PrefillToolCall` carries `tool_def` back-reference. | The property test would have failed: server emits a SIMPLE for a prefilled tool not in `tools=`, SDK registers nothing. |
| `0f715217` | Recurse into `agent.planner` / `agent.fallback` in the four worker-discovery functions. | The property test would have failed: PAE harness's planner sub-agent declares `contextbook_read` in prefill, server emits the SIMPLE under the planner's compiled SUB_WORKFLOW, SDK doesn't recurse. |
| `4e0d2953` | Server adds only stateful tools to `taskToDomain` (not all SIMPLE tasks). | The property test would have failed at the policy boundary: server says `read_repo_docs` → domain X, SDK says `read_repo_docs` → no domain. |

All three are reproducible in `tests/unit/test_worker_contract.py` after this change. None are reproducible in workflows after the runtime invariant check trips.
