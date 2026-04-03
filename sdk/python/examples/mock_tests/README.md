# Mock Tests — Python SDK

## Table of Contents

- [What Is This?](#what-is-this)
- [Why Mock Test Agents?](#why-mock-test-agents)
- [When to Use Mock Tests](#when-to-use-mock-tests)
- [Setup](#setup)
- [Run](#run)
- [Examples](#examples)
- [Quick Reference](#quick-reference)
  - [mock_run](#mock_run)
  - [MockEvent Types](#mockevent-types)
  - [auto_execute_tools](#auto_execute_tools)
  - [Assertions](#assertions)
  - [Fluent API](#fluent-api)
  - [AgentResult](#agentresult)
- [Strategy Validation](#strategy-validation)
- [Record / Replay](#record--replay)
- [CorrectnessEval — Live Agent Evaluation](#correctnesseval--live-agent-evaluation)
- [Testing Pyramid for Agents](#testing-pyramid-for-agents)
- [FAQ](#faq)

---

## What Is This?

The Agentspan testing framework lets you write **deterministic, reproducible tests for AI agents** — without calling an LLM, connecting to a server, or spending API credits. You script the exact sequence of events an agent would produce (tool calls, handoffs, guardrail checks, etc.) and then assert that the agent's structure and behavior are correct.

This is the agent equivalent of unit testing. Just as you wouldn't hit a real database to test your request handler logic, you don't need a real LLM to test that your agent routes to the right specialist, calls tools in the right order, or respects guardrail boundaries.

## Why Mock Test Agents?

**Fast feedback loop.** Mock tests run in milliseconds. No network calls, no token costs, no flaky LLM responses. You can run hundreds of test cases in seconds as part of CI.

**Test orchestration logic, not LLM quality.** The hardest bugs in multi-agent systems aren't about what the LLM says — they're about *routing*: did the right agent get picked? Did tools fire in the right order? Did the guardrail block before the agent acted? Did the pipeline skip a stage? Mock tests catch these structural bugs deterministically.

**Catch regressions early.** When you refactor agent definitions, change tool signatures, or restructure your agent hierarchy, mock tests tell you immediately if the orchestration contract broke — before you burn time on expensive live runs.

**Test edge cases you can't reproduce with an LLM.** What happens when a guardrail fails and retries? When two agents transfer back and forth in a loop? When a tool throws an error mid-pipeline? Mock tests let you script exact scenarios that would be nearly impossible to trigger reliably with a real model.

**Complement live evals, don't replace them.** Mock tests verify *structure* (correct routing, tool usage, event ordering). Live evals with `CorrectnessEval` verify *quality* (did the LLM make good decisions?). Use both: mock tests in CI for fast structural checks, live evals periodically for behavioral validation.

## When to Use Mock Tests

- **CI/CD pipelines** — run on every commit, zero cost, sub-second execution
- **Developing new agents** — validate orchestration logic before wiring up real LLMs
- **Refactoring** — ensure agent restructuring doesn't break routing or tool contracts
- **Edge case coverage** — guardrail failures, error recovery, HITL flows, transfer loops
- **Strategy validation** — verify sequential order, parallel completeness, round-robin alternation, transition constraints
- **Regression testing** — record a known-good run, replay and re-assert later

## Setup

The testing module is included with the SDK. No extra dependencies needed for mock tests.

```bash
# Install the SDK (if not already installed)
uv add agentspan

# The testing module is available at:
#   from agentspan.agents.testing import mock_run, MockEvent, expect, ...
```

For running tests, use `pytest`:

```bash
uv add --dev pytest
```

## Run

```bash
# All mock tests
pytest examples/mock_tests/ -v

# Single file
pytest examples/mock_tests/01_basic_agent.py -v

# Only a specific test class
pytest examples/mock_tests/03_multi_agent_strategies.py::TestHandoff -v

# Only a specific test
pytest examples/mock_tests/01_basic_agent.py::TestBasicCompletion::test_simple_response -v
```

## Examples

| # | File | Topics |
|---|------|--------|
| 01 | `01_basic_agent.py` | `mock_run`, status/output assertions, `expect()` fluent API, `auto_execute_tools`, error and thinking events |
| 02 | `02_tool_assertions.py` | Arg validation (exact + subset), call ordering, exact tool sets, regex output, output type, event sequence, turn budget |
| 03 | `03_multi_agent_strategies.py` | Handoff, Sequential (`>>`), Parallel, Router, Round Robin — routing, handoff targets, agent participation |
| 04 | `04_guardrails_and_errors.py` | Input/output guardrails, guardrail retry, error events, HITL waiting, guardrails in multi-agent flows |
| 05 | `05_advanced_patterns.py` | Swarm + `OnTextMention`, constrained transitions, nested strategies, `validate_strategy`, `record`/`replay` |

Start with `01_basic_agent.py` and work through in order — each file builds on concepts from the previous one.

## Quick Reference

### mock_run

`mock_run()` takes an agent, a prompt, and a scripted list of events, then builds an `AgentResult` you can assert against. No LLM or server is involved.

```python
from agentspan.agents.testing import mock_run, MockEvent

result = mock_run(
    agent,
    "user prompt",
    events=[
        MockEvent.tool_call("search", args={"query": "test"}),
        MockEvent.tool_result("search", result="found it"),
        MockEvent.done("Here's your answer."),
    ],
    auto_execute_tools=False,
)
```

### MockEvent Types

Each factory method creates one event in the scripted execution trace:

| Factory Method | Description |
|---------------|-------------|
| `MockEvent.done(output)` | Final output — completes the run. Every event list must end with this (or `error`). |
| `MockEvent.tool_call(name, args)` | Agent invokes a tool. Pair with `tool_result` when `auto_execute_tools=False`. |
| `MockEvent.tool_result(name, result)` | The return value of a tool call. Not needed when `auto_execute_tools=True`. |
| `MockEvent.handoff(target)` | Agent delegates to a sub-agent by name. |
| `MockEvent.thinking(content)` | LLM reasoning step. Recorded in events but doesn't affect the result status. |
| `MockEvent.message(content)` | Agent sends a message (used in conversational strategies like round-robin). |
| `MockEvent.error(content)` | Error — marks the result status as `FAILED`. |
| `MockEvent.waiting(content)` | Human-in-the-loop pause — agent waits for human approval. |
| `MockEvent.guardrail_pass(name)` | A named guardrail passed validation. |
| `MockEvent.guardrail_fail(name, content)` | A named guardrail blocked the request. |

### auto_execute_tools

Controls whether real tool functions run during `mock_run()`:

| Value | Behavior | When to use |
|-------|----------|-------------|
| `True` (default) | Your `@tool` functions execute for real. You only need `MockEvent.tool_call` — the result is computed automatically. | When you want to test tool *implementations* alongside orchestration. |
| `False` | Tools don't execute. You must provide both `MockEvent.tool_call` and `MockEvent.tool_result` for every call. | When you want to control exact inputs/outputs and test orchestration *logic* in isolation. |

### Assertions

All assertion functions take an `AgentResult` as the first argument and raise `AssertionError` on failure:

| Function | What it checks |
|----------|---------------|
| `assert_status(result, status)` | Result status matches (e.g. `"COMPLETED"`, `"FAILED"`) |
| `assert_no_errors(result)` | No `ERROR` events in the trace |
| `assert_tool_used(result, name)` | Tool was called at least once |
| `assert_tool_not_used(result, name)` | Tool was never called |
| `assert_tool_called_with(result, name, args=...)` | Tool was called with specific args (subset match — extra args OK) |
| `assert_tool_call_order(result, names)` | Tools appeared in this subsequence order (other calls in between OK) |
| `assert_tools_used_exactly(result, names)` | Exactly these tools were used — no more, no less (set equality) |
| `assert_output_contains(result, text, case_sensitive=True)` | Final output contains substring |
| `assert_output_matches(result, pattern)` | Final output matches regex pattern |
| `assert_output_type(result, type_)` | Final output is an instance of the given type |
| `assert_handoff_to(result, agent_name)` | A handoff to this agent occurred |
| `assert_agent_ran(result, agent_name)` | Agent participated (appeared in a handoff event) |
| `assert_guardrail_passed(result, name)` | Named guardrail passed |
| `assert_guardrail_failed(result, name)` | Named guardrail failed/blocked |
| `assert_event_sequence(result, types)` | Event types appear in this subsequence order |
| `assert_events_contain(result, event_type, expected=True)` | Event type exists (or doesn't) in the trace |
| `assert_max_turns(result, n)` | Agent didn't exceed `n` turns (tool calls + done events) |

```python
from agentspan.agents.testing import (
    assert_status, assert_no_errors,
    assert_tool_used, assert_tool_not_used,
    assert_tool_called_with, assert_tool_call_order,
    assert_tools_used_exactly,
    assert_output_contains, assert_output_matches, assert_output_type,
    assert_handoff_to, assert_agent_ran,
    assert_guardrail_passed, assert_guardrail_failed,
    assert_event_sequence, assert_events_contain,
    assert_max_turns,
)
```

### Fluent API

The `expect()` API chains multiple assertions in a single expression. Every method returns `self`, so you keep chaining. It raises on the first failure.

```python
from agentspan.agents.testing import expect

(expect(result)
    .completed()                                    # status == "COMPLETED"
    .used_tool("search", args={"query": "test"})    # tool called with these args
    .did_not_use_tool("delete")                     # tool was NOT called
    .handoff_to("specialist")                       # handoff occurred
    .agent_ran("researcher")                        # agent participated
    .output_contains("answer")                      # output has substring
    .output_matches(r"order #\d+")                  # output matches regex
    .guardrail_passed("pii_check")                  # guardrail passed
    .max_turns(10)                                  # didn't exceed 10 turns
    .no_errors())                                   # no ERROR events
```

You can also assert failure:

```python
expect(result).failed()  # status != "COMPLETED"
```

### AgentResult

`mock_run()` returns an `AgentResult` with these key properties:

| Property | Type | Description |
|----------|------|-------------|
| `result.output` | `Any` | The final answer (string, dict, or structured type) |
| `result.status` | `Status` | `COMPLETED`, `FAILED`, `TERMINATED`, or `TIMED_OUT` |
| `result.events` | `list[AgentEvent]` | Full execution trace — every tool call, handoff, guardrail, etc. |
| `result.tool_calls` | `list[dict]` | All tool invocations with names and arguments |
| `result.messages` | `list[dict]` | Conversation history |
| `result.error` | `str | None` | Error message if the run failed |
| `result.is_success` | `bool` | `True` if status is `COMPLETED` |
| `result.is_failed` | `bool` | `True` if status is `FAILED`, `TERMINATED`, or `TIMED_OUT` |
| `result.finish_reason` | `FinishReason` | Why the agent stopped: `STOP`, `ERROR`, `GUARDRAIL`, `TIMEOUT`, etc. |

Each `AgentEvent` has:

| Property | Type | Description |
|----------|------|-------------|
| `event.type` | `EventType` | `TOOL_CALL`, `HANDOFF`, `DONE`, `ERROR`, `GUARDRAIL_PASS`, etc. |
| `event.target` | `str` | Agent name (for `HANDOFF` events) |
| `event.name` | `str` | Tool or guardrail name (for `TOOL_CALL`, `GUARDRAIL_*` events) |
| `event.content` | `Any` | Event payload (tool args, output text, error message, etc.) |

---

## Strategy Validation

`validate_strategy(agent, result)` inspects the full execution trace and verifies that the orchestration rules for the agent's declared strategy were actually followed. Unlike individual assertions that check one property at a time, strategy validation checks the **structural correctness of the entire run** — catching bugs where agents were skipped, ran out of order, looped, or violated transition constraints.

It works on both mock and live results. When used with live results from `CorrectnessEval`, it catches real orchestration bugs that would be invisible to output-only checks.

```python
from agentspan.agents.testing import validate_strategy, StrategyViolation

# Passes silently if the trace matches the strategy rules
validate_strategy(agent, result)

# Raises StrategyViolation with a descriptive message on failure
# e.g. "Sequential violation: agent 'writer' was skipped"
```

Each strategy has specific rules that are validated:

| Strategy | What it checks |
|----------|---------------|
| **Sequential** | All agents ran, in definition order, exactly once each. Catches skipped agents and wrong ordering. |
| **Parallel** | All agents ran (order doesn't matter). Catches any agent that was skipped. |
| **Round Robin** | Agents alternate in the correct rotation pattern. Catches wrong starting agent, same agent running twice in a row, and exceeded `max_turns`. |
| **Router** | Exactly one sub-agent was selected. Catches zero selections (router handled it itself) and multiple selections. |
| **Handoff** | At least one handoff occurred to a valid sub-agent. |
| **Swarm** | At least one agent handled the request, no transfer loops (same pair ping-ponging >2 times), respects `max_turns`. |
| **Constrained** | Every transition in the trace is present in the `allowed_transitions` dict. Catches illegal jumps (e.g. L1 directly to L3 when only L1→L2 is allowed). |

You can also call individual validators directly:

```python
from agentspan.agents.testing.strategy_validators import (
    validate_sequential,
    validate_parallel,
    validate_round_robin,
    validate_router,
    validate_handoff,
    validate_swarm,
    validate_constrained_transitions,
)

# Useful when an agent uses round_robin + allowed_transitions
# and you want to check the constraint rules specifically
validate_constrained_transitions(agent, result)
```

---

## Record / Replay

Record/replay lets you capture an `AgentResult` to a JSON file, then load it back later to re-run assertions against it. **Replay does not re-execute anything** — no server, no LLM, no mock run. It simply deserializes the saved result into an `AgentResult` object so you can assert against the same frozen snapshot.

This is the foundation for **regression testing** — you record a known-good result once, commit the fixture to version control, and your CI re-asserts against it on every build. If someone changes the agent definition and the assertions start failing, you know the contract broke.

**How it works:**

```
record(result, path)  →  serializes AgentResult to JSON on disk
replay(path)          →  deserializes JSON back into an AgentResult (no execution)
```

The execution happens *before* recording — either via `mock_run()` (deterministic, no server) or a real live run with `CorrectnessEval` (real LLM). `record()` saves whatever result you give it. `replay()` loads it back. That's it.

**Why this matters:** Agent definitions evolve — you add tools, restructure sub-agents, change instructions. Without regression fixtures, the only way to know if you broke something is to run a live eval (slow, expensive, non-deterministic). With record/replay, you get instant deterministic regression checks.

**Typical workflow:**

1. Run your agent (mock or live) and verify it behaves correctly
2. `record()` the result to a JSON fixture file
3. Commit the fixture to version control
4. In CI, `replay()` the fixture and re-assert — if assertions fail, the agent's contract changed

```python
from agentspan.agents.testing import mock_run, record, replay, expect, MockEvent

# Step 1: Run the agent and record the result
result = mock_run(agent, "Track order #123", events=[
    MockEvent.handoff("shipping_specialist"),
    MockEvent.tool_call("track_shipment", args={"tracking_id": "TRK-001"}),
    MockEvent.tool_result("track_shipment", result={"status": "delivered"}),
    MockEvent.done("Your package has been delivered!"),
])
record(result, "fixtures/track_order.json")

# Step 2: Later (in CI, after refactoring, etc.)
# replay() just loads the JSON — nothing is executed
replayed = replay("fixtures/track_order.json")

(expect(replayed)
    .completed()
    .handoff_to("shipping_specialist")
    .used_tool("track_shipment")
    .output_contains("delivered")
    .no_errors())
```

The fixture JSON contains the full execution snapshot: agent metadata, prompt, all events, tool calls, messages, status, and output. It's human-readable and diffable, so you can review what changed when a regression test fails.

**Recording live runs:** You can also record results from real `CorrectnessEval` executions (with actual LLM calls). This captures the real LLM behavior as a fixture, so future CI runs can replay and re-assert without spending API credits or needing a running server.

---

## CorrectnessEval — Live Agent Evaluation

`CorrectnessEval` is the **live counterpart to mock tests**. While `mock_run()` scripts behavior without an LLM, `CorrectnessEval` runs your agents against a **real Agentspan server with real LLM calls** and checks whether the agent's actual behavior matches your expectations.

This is where you test that the LLM actually makes the right decisions — not just that the orchestration wiring is correct.

**What it requires:**
- A running Agentspan server (`CONDUCTOR_SERVER_URL` env var)
- An `AgentRuntime` instance connected to it
- API keys for the LLM providers your agents use (e.g. `OPENAI_API_KEY`)
- Real token costs (each eval case makes live LLM calls)

**How it works:**

1. You define `EvalCase` objects describing: what prompt to send, what correct behavior looks like
2. `CorrectnessEval` runs each case through `runtime.run()` — real LLM, real tools, real orchestration
3. It checks every expectation and produces a pass/fail report

```python
from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from agentspan.agents.testing import CorrectnessEval, EvalCase

# Define your agents (same ones you'd mock test)
billing_agent = Agent(name="billing", model="openai/gpt-4o", ...)
technical_agent = Agent(name="technical", model="openai/gpt-4o", ...)
support = Agent(
    name="support",
    agents=[billing_agent, technical_agent],
    strategy=Strategy.HANDOFF,
)

# Connect to a real server
with AgentRuntime() as runtime:
    eval = CorrectnessEval(runtime)

    results = eval.run([
        EvalCase(
            name="billing_routes_correctly",
            agent=support,
            prompt="I need a refund for order #123",
            expect_handoff_to="billing",
            expect_tools=["lookup_order"],
            expect_output_contains=["refund"],
            expect_tools_not_used=["search_web"],
        ),
        EvalCase(
            name="tech_routes_correctly",
            agent=support,
            prompt="My app keeps crashing on startup",
            expect_handoff_to="technical",
            expect_tools=["search_web"],
            expect_tools_not_used=["lookup_order", "process_refund"],
        ),
        EvalCase(
            name="sequential_pipeline_all_stages",
            agent=content_pipeline,
            prompt="Write about quantum computing",
            validate_orchestration=True,  # auto-runs validate_strategy()
        ),
    ])

    results.print_summary()
    assert results.all_passed, f"{results.fail_count} eval(s) failed"
```

**EvalCase fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | `""` | Descriptive name for the test case |
| `agent` | `Agent` | — | The agent to test |
| `prompt` | `str` | `""` | The user message to send |
| `expect_tools` | `list[str]` | `None` | Tools that MUST be used |
| `expect_tools_not_used` | `list[str]` | `None` | Tools that must NOT be used |
| `expect_tool_args` | `dict[str, dict]` | `None` | Tool must be called with specific args (`{tool_name: {arg: val}}`) |
| `expect_handoff_to` | `str` | `None` | Agent name that should receive the handoff |
| `expect_no_handoff_to` | `list[str]` | `None` | Agent names that should NOT receive handoffs |
| `expect_output_contains` | `list[str]` | `None` | Substrings the output must contain (case-insensitive) |
| `expect_output_matches` | `str` | `None` | Regex pattern the output must match |
| `expect_status` | `str` | `"COMPLETED"` | Expected terminal status |
| `expect_no_errors` | `bool` | `True` | Assert no error events in the trace |
| `validate_orchestration` | `bool` | `True` | Run `validate_strategy()` on the result |
| `custom_assertions` | `list[Callable]` | `[]` | Extra assertion functions `(result) -> None` |
| `tags` | `list[str]` | `[]` | Tags for filtering (`eval.run(cases, tags=["smoke"])`) |

**Sample output:**

```
============================================================
 Agent Correctness Eval Results
============================================================

  [PASS] billing_routes_correctly
  [PASS] tech_routes_correctly
  [FAIL] sequential_pipeline_all_stages
         x strategy_validation: Sequential violation: agent 'editor' was skipped

────────────────────────────────────────────────────────────
  2/3 passed, 1 failed
============================================================
```

---

## Testing Pyramid for Agents

| Layer | Tool | Runs against | Cost | Speed | What it catches | CI cadence |
|-------|------|-------------|------|-------|-----------------|------------|
| **Unit** | `mock_run` | Nothing — scripted events | Free | Milliseconds | Broken routing, wrong tool order, missing agents, constraint violations | Every commit |
| **Structural** | `validate_strategy` | Mock or live `AgentResult` | Free | Milliseconds | Strategy-level bugs: skipped pipeline stages, broken rotation, transfer loops | Every commit |
| **Regression** | `record` / `replay` | Saved JSON fixture | Free | Milliseconds | Changes to orchestration contracts after refactoring | Every commit |
| **Integration** | `CorrectnessEval` | Real server + real LLM | API credits | Seconds per case | LLM picking wrong agent, bad tool args, poor output quality | Nightly / weekly |

Start from the bottom — write mock tests first, add strategy validation, record fixtures, and run live evals periodically.

---

## FAQ

### Do I need a running server for mock tests?

No. `mock_run()` is entirely local. No server, no LLM, no network calls, no API keys. That's the whole point.

### Do I need a running server for `record()` / `replay()`?

No. `record()` takes an `AgentResult` you already have (from `mock_run()`) and saves it to JSON. `replay()` reads it back. Neither touches a server.

The only time a server is involved is if you first run an agent with `CorrectnessEval` (live execution), then pass *that* result to `record()`. But that's your choice — `record()` itself is just serialization.

### What's the difference between `assert_tool_called_with` and `assert_tools_used_exactly`?

- `assert_tool_called_with(result, "search", args={"query": "test"})` — checks that `search` was called with at least these args (subset match). Other args and other tool calls are ignored.
- `assert_tools_used_exactly(result, ["search", "fetch"])` — checks that *exactly* these tools were used, no more, no less. Doesn't check args.

### What does `auto_execute_tools=True` actually do?

When `True` (default), `mock_run()` calls your real `@tool` functions when it encounters a `MockEvent.tool_call`. The return value becomes the tool result automatically — you don't need `MockEvent.tool_result` events.

When `False`, tools are not executed. You must script both `MockEvent.tool_call` and `MockEvent.tool_result` for every tool invocation. This gives you full control over inputs and outputs.

### Can I mix assertions and the fluent `expect()` API?

Yes. They use the same underlying checks. Use whichever style you prefer, or mix them in the same test:

```python
assert_tool_used(result, "search")
expect(result).completed().output_contains("found").no_errors()
```

### How do I test that an agent does NOT hand off to a specific agent?

Use `pytest.raises`:

```python
with pytest.raises(AssertionError):
    assert_handoff_to(result, "wrong_agent")
```

Or use `assert_events_contain` with `expected=False`:

```python
assert_events_contain(result, EventType.HANDOFF, expected=False, target="wrong_agent")
```

### How does `assert_event_sequence` work?

It checks a **subsequence** — the listed event types must appear in this order, but other events can appear in between. For example:

```python
# This passes even if there are THINKING events between the TOOL_CALLs
assert_event_sequence(result, [EventType.TOOL_CALL, EventType.TOOL_CALL, EventType.DONE])
```

### Can I run `CorrectnessEval` with pytest?

Yes. Mark your live tests with `@pytest.mark.integration` and skip them by default:

```python
@pytest.mark.integration
class TestLiveEvals:
    @pytest.fixture
    def runtime(self):
        from agentspan.agents import AgentRuntime
        with AgentRuntime() as rt:
            yield rt

    def test_routing(self, runtime):
        eval = CorrectnessEval(runtime)
        results = eval.run([...])
        assert results.all_passed
```

Run with: `pytest -m integration`

### What happens if my events list doesn't end with `MockEvent.done()` or `MockEvent.error()`?

The result will still be constructed from whatever events you provide, but the status may not be set correctly. Always end with `done()` for success or `error()` for failure.
