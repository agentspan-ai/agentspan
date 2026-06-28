# Guardrails Design

**Status:** Consolidated 2026-06-26

**Scope.** Guardrails validate agent inputs and outputs, preventing unsafe, non-compliant, or malformed content from reaching users — and, just as importantly, preventing an agent from taking unsafe *actions* via its tools. This document is the canonical reference for the guardrails feature: the user-facing model and API (guardrail types, the five checkpoints, failure modes), how each guardrail compiles into Conductor workflow tasks (so retries, escalations, and fixes are durable and visible in the Conductor UI), worked recipes, and a condensed industry analysis explaining the design rationale. For the broader agent runtime see [agentspan-design.md](agentspan-design.md); for the language SDK surface see [sdk-design.md](sdk-design.md); for the REST/control-plane API see [api-design.md](api-design.md).

---

## 1. Scope

A guardrail answers one question: **"Should this content be allowed to proceed?"** — and, on failure, *what should we do about it*. Guardrails integrate directly into Conductor execution so that retries, escalations, and fixes are:

- **Durable** — they survive worker and client crashes (they are workflow state, not in-memory state).
- **Visible** — each check appears as a task in the Conductor UI, with full status and logs.
- **Compatible** — they work with every execution mode (`run()`, `start()`, `stream()`).

Guardrails attach to an **agent** (validate LLM input/output) or to a **tool** (validate tool I/O — the highest-risk checkpoint, because tools take real-world actions).

Code samples below use the Python SDK. The model has **identical enums/types** across SDKs (`OnFail`, `Position`, `GuardrailResult`), but **construction is idiomatic per SDK**: Python `Guardrail(func, ...)`; Java `Guardrail.of(name, func)...build()` plus `Guardrail.external(name)`; TypeScript `guardrail(fn, {...})` plus `guardrail.external()` and the `@Guardrail` decorator; C# `[Guardrail]` attribute / options-style `Create(...)` factories (see [sdk-design.md](sdk-design.md)).

```python
import re
from conductor.ai.agents import (
    Agent, AgentRuntime, Guardrail, GuardrailResult,
    OnFail, Position, guardrail, tool,
)

# 1. Define a guardrail with the @guardrail decorator
@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses containing credit card numbers."""
    if re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", content):
        return GuardrailResult(
            passed=False,
            message="Redact all credit card numbers before responding.",
        )
    return GuardrailResult(passed=True)

# 2. Define a tool
@tool
def get_customer(customer_id: str) -> dict:
    """Look up customer profile."""
    return {"name": "Alice", "card": "4532-0150-1234-5678"}

# 3. Attach the guardrail to the agent
agent = Agent(
    name="support",
    model="openai/gpt-4o",
    tools=[get_customer],
    guardrails=[
        Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY),
    ],
)

# 4. Run — the guardrail retries automatically inside the execution
with AgentRuntime() as runtime:
    result = runtime.run(agent, "Show me customer CUST-7's full profile.")
    print(result.output)  # Credit card number will be redacted
```

> **Note:** Plain strings (`"output"`, `"retry"`) still work — `OnFail` and `Position` are `str` enums for discoverability and IDE autocompletion.

---

## 2. Guardrail model & API

A guardrail is a function `(content: str) -> GuardrailResult` that returns pass/fail (and optionally a corrected output). The lifecycle:

1. The LLM generates a response (or a tool produces output).
2. Each guardrail runs against that content in order.
3. On the first failure, the `on_fail` strategy decides what happens.

### 2.1 The five checkpoints

The agent execution loop has five natural checkpoints where guardrails can intercept. Two map to the SDK's `Position` values today; the others are realized through tool guardrails and pre-model context validation.

| # | Checkpoint | When | What it catches | Cost of failure |
|---|-----------|------|-----------------|-----------------|
| 1 | **Input** | Before the agent loop starts | Prompt injection, malformed input, off-topic requests | Low (no work done yet) |
| 2 | **Pre-model** | Before each LLM call in the loop | Context poisoning, accumulated injection | Medium |
| 3 | **Post-model** | After the LLM responds, before tool dispatch | Hallucinated tool calls, unsafe reasoning | High (about to act) |
| 4 | **Tool** | Around each tool execution | Dangerous parameters, sensitive data in args/results | Critical (action taken) |
| 5 | **Output** | Before returning the final answer | PII, policy violations, quality issues | Medium (text only) |

The `Position` enum exposes the two most-used checkpoints:

```python
class Position(str, Enum):
    INPUT  = "input"   # Before the LLM call (or before a tool runs)
    OUTPUT = "output"  # After the LLM call (or after a tool runs)
```

**Key insight (see §5):** most SDKs only implement checkpoints 1 and 5. For agents the highest risk is at 3 and 4 — where the model decided to call a dangerous tool, or the tool is about to execute with bad parameters. Tool guardrails (§3.3) cover these.

### 2.2 Failure modes (`on_fail`)

```python
class OnFail(str, Enum):
    RETRY = "retry"    # Ask the LLM to try again with feedback
    RAISE = "raise"    # Fail the execution immediately
    FIX   = "fix"      # Use GuardrailResult.fixed_output
    HUMAN = "human"    # Pause for human review (output only)
```

**Default `on_fail` is now uniform `raise` across all four SDKs** (Python, TypeScript, Java, C#) — for every guardrail kind (`guardrail()`/custom, `guardrail.external()`, the `@Guardrail`/`[Guardrail]` decorator/attribute, `RegexGuardrail`, `LLMGuardrail`). This matches the server's routing, which also falls back to `raise` when `on_fail` is null. (Earlier divergence — Python/Java defaulting to `retry`, C# mixed — has been removed; every SDK serializes an explicit `raise` unless overridden.)

| Mode | Behavior | Best for |
|------|----------|----------|
| `retry` | Feedback appended to the conversation; the LLM retries. After `max_retries` is exhausted, escalates to `raise`. | Quality/format/PII issues the LLM can self-correct. |
| `fix` | Uses `GuardrailResult.fixed_output` directly — no LLM retry. | Deterministic corrections (regex substitution, sanitization). Faster and cheaper. |
| `raise` | Terminates the execution with `FAILED` status and the guardrail message as the reason. | Hard security blocks, zero-tolerance policies, input validation. |
| `human` | Pauses at a HumanTask; a human approves, edits, or rejects. **Only valid for `position="output"`** — input guardrails run client-side and cannot pause an execution. (This constraint is now enforced at construction in **all four SDKs** — Python, TypeScript, Java, and C# — each rejecting the `human`+`input` combination.) | Compliance review, content moderation, sensitive decisions. |

**Retry escalation.** `max_retries` controls how many times `retry` attempts before escalating to `raise` (default `3`). The minimum is `1`: the Python SDK rejects `max_retries < 1` with a `ValueError`, so `0` is **invalid**, not "equivalent to raise". Each guardrail carries its own `max_retries`. For client-side guardrails (simple agents without tools), the runtime uses the maximum across all output guardrails. This prevents infinite retry loops.

#### `human` usage with `start()`

`run()` would block, so use `start()` when an execution may pause:

```python
with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Give me investment advice.")

    import time
    while True:
        status = handle.get_status()
        if status.is_waiting:
            print("Paused for human review")
            runtime.approve(handle.execution_id)          # accept as-is
            # or: runtime.reject(handle.execution_id, reason="...")   # terminate FAILED
            # or: runtime.respond(handle.execution_id, {"edited_output": "..."})  # replace
            break
        if status.is_complete:
            break
        time.sleep(1)

    print(handle.get_status().output)
```

### 2.3 Guardrail types

| Type | What it does | Compiles to (see §3) | Output path |
|------|--------------|----------------------|-------------|
| `Guardrail` (custom fn) | Wrap any Python function | SIMPLE worker + normalize InlineTask | `${ref}.output.result.*` |
| `RegexGuardrail` | Pattern block/allow lists | InlineTask (JavaScript, GraalVM) | `${ref}.output.result.*` |
| `LLMGuardrail` | Judge content with a second LLM against a policy | `LlmChatComplete` + InlineTask parser | `${ref}.output.result.*` |
| External | Reference a remote worker by name | SimpleTask | `${ref}.output.*` |

#### `Guardrail` (custom function)

```python
guard = Guardrail(
    func=check_length,
    position="output",   # "input" or "output"
    on_fail="retry",     # "retry", "raise" (default), "fix", or "human"
    name="length_check", # Optional, defaults to function name
    max_retries=3,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `func` | `Callable[[str], GuardrailResult]` | *required* (unless external) | Validation function |
| `position` | `str` | `"output"` | `"input"` or `"output"` |
| `on_fail` | `str` | `"raise"` | `"retry"`, `"raise"`, `"fix"`, `"human"` (default uniform `raise` across all four SDKs) |
| `name` | `str` | function name | Human-readable identifier |
| `max_retries` | `int` | `3` | Max retries for `on_fail="retry"` |

**External guardrails** — pass `name` without `func` to reference a guardrail worker running elsewhere (any language). Its `external` attribute is `True`.

```python
Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)
```

Worker contract: input `{"content": "<text>", "iteration": <n>}`, output `{"passed": bool, "message": str, "on_fail": str, "should_continue": bool}`.

#### `RegexGuardrail`

```python
# Block mode (default): reject content matching any pattern
no_emails = RegexGuardrail(
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    mode="block",
    name="no_emails",
    message="Do not include email addresses in your response.",
)

# Allow mode: reject content that does NOT match at least one pattern
json_only = RegexGuardrail(
    patterns=[r"^\s*[\{\[]"],
    mode="allow",
    name="json_only",
    message="Response must be valid JSON.",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `patterns` | `str \| List[str]` | *required* | Regex patterns |
| `mode` | `str` | `"block"` | `"block"` (reject matches) or `"allow"` (reject non-matches) |
| `message` | `str` | auto-generated | Custom failure message |
| `position` | `str` | `"output"` | `"input"` or `"output"` |
| `on_fail` | `str` | `"raise"` | Failure strategy (default uniform `raise` across all four SDKs) |
| `max_retries` | `int` | `3` | Max retries |

#### `LLMGuardrail`

```python
safety = LLMGuardrail(
    model="anthropic/claude-sonnet-4-6",  # use a fast, cheap model
    policy=(
        "Reject any content that:\n"
        "1. Contains medical or legal advice presented as fact\n"
        "2. Makes promises or guarantees about outcomes\n"
        "3. Includes discriminatory or biased language"
    ),
    name="content_safety",
    on_fail="retry",
)
```

The judge LLM receives the policy + content and returns `{"passed": true/false, "reason": "..."}`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | *required* | `"provider/model"` format |
| `policy` | `str` | *required* | Natural-language policy for the judge |
| `position` | `str` | `"output"` | `"input"` or `"output"` |
| `on_fail` | `str` | `"raise"` | Failure strategy (default uniform `raise` across all four SDKs) |
| `max_retries` | `int` | `3` | Max retries |
| `max_tokens` | `int` | SDK default | Max tokens for the judge LLM response (supported in Python, TypeScript, C#, and the server `GuardrailCompiler`) |

> When compiled (§3.4) the judge call runs **server-side** as an `LlmChatComplete` task and needs no client dependency. When run client-side it uses `litellm` (`pip install litellm`); pick a fast model either way to avoid slowing the agent loop.

### 2.4 `GuardrailResult` and the `@guardrail` decorator

```python
@dataclass
class GuardrailResult:
    passed: bool                         # True if content passes validation
    message: str = ""                    # Feedback for the LLM (used on retry)
    fixed_output: Optional[str] = None   # Corrected output (used with on_fail="fix")
```

```python
@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject PII."""
    ...

@guardrail(name="pii_checker")   # custom name
def no_pii(content: str) -> GuardrailResult: ...
```

The decorator attaches a `_guardrail_def` attribute (a `GuardrailDef` dataclass) and keeps the function callable, so `@guardrail` functions are usable standalone — without an agent or a server:

```python
result = no_pii("Some text to validate")
print(result.passed, result.message)
```

They can also be deployed as standalone Conductor workers, letting any agent in any language reference them by name (external guardrails, above). `Guardrail()` auto-detects decorated functions.

### 2.5 Constructor signatures (reference)

```python
class Guardrail:
    def __init__(
        self,
        func: Optional[Callable[[str], GuardrailResult]] = None,
        position: str = "output",
        on_fail: str = "raise",          # uniform default across all four SDKs
        name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None: ...
    external: bool                       # True when func is None
    def check(self, content: str) -> GuardrailResult: ...

class RegexGuardrail(Guardrail):
    def __init__(self, patterns, *, mode="block", position="output",
                 on_fail="raise", name=None, message=None, max_retries=3): ...

class LLMGuardrail(Guardrail):
    def __init__(self, model, policy, *, position="output",
                 on_fail="raise", name=None, max_retries=3, max_tokens=None): ...
```

```python
@tool(guardrails=[guard1, guard2])
def my_tool(param: str) -> str: ...

Agent(name="...", model="...", guardrails=[guard1, guard2])
```

---

## 3. Conductor compilation

Conductor already has every building block needed; the design is about composition. Guardrails behave differently depending on whether the agent has tools — but the user-facing API is the same.

| Conductor construct | Guardrail role |
|---------------------|----------------|
| `worker_task` | Runs a custom/regex/LLM guardrail; result is durable workflow state. |
| `LlmChatComplete` | Server-side LLM guardrails (replaces client-side litellm). |
| `SwitchTask` | Routes on `{passed, message, on_fail}` to retry / raise / fix / human. |
| `DoWhileTask` | The agent loop; output guardrails insert into its body. |
| `SetVariableTask` | Appends retry feedback to `workflow.variables.messages` — no full re-execution. |
| `TerminateTask` | `on_fail="raise"` / tripwire — terminate `FAILED` with the guardrail reason. |
| `HumanTask` | `on_fail="human"` — durable, assignable, auditable escalation. |
| `ForkTask` + `JoinTask` | Run multiple guardrails in parallel (§3.5). |
| `InlineTask` | Regex eval, LLM-response parsing, score aggregation. |
| `SubWorkflowTask` | Package a guardrail chain for reuse across agents. |

### 3.1 Output guardrails in the DoWhile loop (agents with tools)

The agent loop body, before/after guardrails are compiled in:

```
DoWhile (before):
  [1. LlmChatComplete]
  [2. SwitchTask (tool_call vs final_answer)]

DoWhile (with guardrails):
  [1. LlmChatComplete]
  [2. Guardrail check task]            <-- NEW: evaluates LLM output
  [3. SwitchTask on guardrail result]  <-- NEW: routes on pass/fail
       -> "pass":  [original SwitchTask (tool_call vs final_answer)]
       -> "retry": [SetVariable: append feedback to messages]  -> loop continues
       -> "raise": [TerminateTask(FAILED, reason)]
       -> "fix":   [SetVariable: use fixed_output] -> [original SwitchTask]
       -> "human": [HumanTask] -> [SwitchTask on human decision]
                                    -> approve: continue
                                    -> edit:    use edited output
                                    -> reject:  TerminateTask(FAILED)
```

The SwitchTask reads `on_fail` from a type-dependent path (tracked by an `is_inline` flag from `_compile_output_guardrail_tasks()`):

| Guardrail type | Output path |
|----------------|-------------|
| RegexGuardrail / LLMGuardrail (InlineTask) | `$.{ref}.result.on_fail` |
| Custom function (SIMPLE worker + normalize INLINE) | `$.{ref}.result.on_fail` |
| External (SimpleTask) | `$.{ref}.on_fail` |

Custom guardrails compile to a **SIMPLE worker task plus a normalize INLINE task**; the routing SWITCH reads the INLINE task's output, so the path is `output.result.on_fail` (not `output.on_fail`).

**Retry via feedback injection.** On `on_fail="retry"` the guardrail returns:

```json
{ "passed": false, "message": "Response contains a credit card number. Redact all PII.",
  "on_fail": "retry", "should_continue": true }
```

A SetVariable appends a system message and the loop iterates back to the LLM — **no full workflow re-execution**:

```python
set_retry = SetVariableTask(task_ref_name="guardrail_retry_feedback")
set_retry.input_parameter("messages", [
    ...existing_messages,
    {"role": "system",
     "message": "[Guardrail: ${guardrail.output.message}. Please revise your response.]"},
])
```

**Termination-condition integration.** When retry guardrails exist, their `should_continue` flag is ANDed into the loop condition so the loop keeps going on retry:

```javascript
iteration < max_turns
  && finishReason != 'LENGTH'
  && (toolCalls != null || guardrail_should_continue)
```

### 3.2 Simple agents (no tools) and input guardrails

**Simple agents (client-side output).** With no tools there is no DoWhile loop, so output guardrails run client-side after each execution: execute → check → on retry, modify the prompt and re-execute the whole agent. Simpler, but less efficient (full re-execution per retry).

**Input guardrails (always client-side).** `position="input"` runs once, before workflow submission. Only `raise`/`human`-block semantics are meaningful — there is no LLM to retry against. This is intentional: fast rejection saves server resources (the workflow is never created), and there is no durability benefit to a one-shot pre-submission check.

```python
# In runtime.run(), before workflow submission
for guard in agent.guardrails:
    if guard.position == "input":
        result = guard.check(prompt)
        if not result.passed:
            raise ValueError(f"Input guardrail '{guard.name}' failed: {result.message}")
```

### 3.3 Tool guardrails

Tool calls are the highest-risk checkpoint because they take **real-world actions** — a hallucinated `send_email(to="all@company.com")`, PII flowing from a database into LLM context, SQL injection in a query parameter. Pre-tool guardrails catch dangerous inputs; post-tool guardrails sanitize dangerous outputs.

```python
@tool(guardrails=[Guardrail(no_sql_injection, position="input", on_fail="raise")])
def run_query(query: str) -> str: ...
```

Tool guardrails have **two execution paths**, and both exist in the codebase:

**1. Client-side, in-process (Python-run tools).** When the tool runs as a Python worker, its guardrails are wrapped **inside the tool worker process** by `make_tool_worker()` (`runtime/_dispatch.py`) — the check happens within the existing tool task, not as a separate workflow task:

- **`position="input"`** — runs before the tool. Receives a JSON string of all input kwargs. On failure with `raise`, raises `ValueError`; otherwise returns `{error: ..., blocked: True}` and the tool is skipped.
- **`position="output"`** — runs after the tool. Receives the result as a string. On `fix`, replaces the result with `fixed_output`; on `raise`, raises `ValueError`.

**2. Server-compiled gate tasks (separate workflow tasks).** Python serializes each tool's guardrails into the tool config (`config_serializer.py`), so the **server compiler builds them as real, separate workflow tasks**. `ToolCompiler.java` (`collectToolGuardrails`, `buildToolGuardrailGate`, with `compileToolGuardrailTasks` in `GuardrailCompiler.java`) prepends a **guardrail gate before the `DynamicFork`** of tool workers. The gate is:

```
tool_call branch:
  [format INLINE: _format_tool_calls]   <-- build guardrail input from tool calls
  [guardrail task(s)]                    <-- SIMPLE/INLINE/LLM per guardrail kind
  [routing SWITCH]                       <-- pass / raise / fix per on_fail
  -> pass: [DynamicFork(tool workers)]   <-- the gate runs BEFORE the fork
```

So the same authoring API maps to client-side in-process checks for Python-run tools, and to server-compiled gate tasks (durable, visible in the Conductor UI) otherwise.

### 3.4 Server-side vs client-side LLM guardrails

Client-side (`litellm` in the worker process) requires a dependency, isn't visible in the UI, and gets no Conductor retry/timeout policies. The compiled form is a server-side `LlmChatComplete` task:

```python
guardrail_llm = LlmChatComplete(
    task_ref_name=f"{agent_name}_guardrail_llm",
    llm_provider="openai",          # server-configured provider — no extra keys
    model="anthropic/claude-sonnet-4-6",
    messages=[
        ChatMessage(role="system", message=guardrail_policy_prompt),
        ChatMessage(role="user", message="${llm_output}"),
    ],
    temperature=0.0, max_tokens=200, json_output=True,
)
```

It is followed by an InlineTask that parses `passed`/`reason` and maps `on_fail`. Choosing a construct per guardrail kind:

| Construct | When to use |
|-----------|-------------|
| `worker_task` (Python) | Custom logic, regex, DB lookups |
| `LlmChatComplete` (server) | Policy evaluation, content classification |
| `InlineTask` (JavaScript) | Threshold/pattern checks, score aggregation |

### 3.5 Parallel guardrails via ForkTask

Run independent guardrails (PII + toxicity + policy) concurrently, then aggregate:

```
[LlmChatComplete output] -> [ForkTask: PII | Toxicity | Policy] -> [JoinTask]
  -> [InlineTask: aggregate] -> [SwitchTask] -> pass: continue / fail: on_fail handler
```

```javascript
(function() {
  var results = [$.pii_guard.output, $.toxicity_guard.output, $.policy_guard.output];
  var failed = results.filter(function(r) { return !r.passed; });
  if (failed.length === 0) return { passed: true, on_fail: "pass" };
  // Priority: raise > human > retry > fix — return the most severe failure
  var priority = { "raise": 4, "human": 3, "retry": 2, "fix": 1 };
  failed.sort(function(a, b) { return (priority[b.on_fail] || 0) - (priority[a.on_fail] || 0); });
  return failed[0];
})()
```

### 3.6 Multi-agent guardrail wrapping

When a multi-agent strategy workflow has output guardrails, the whole strategy is wrapped in an outer DoWhile, which re-runs the full strategy on retry:

```
DoWhile (guardrail_loop)
  ├─ InlineSubWorkflow (strategy workflow)
  ├─ [Guardrail check task(s)]
  └─ [Guardrail routing SwitchTask(s)]
```

### 3.7 Why compiled beats client-side

| Aspect | Client-side | Compiled into workflow |
|--------|-------------|------------------------|
| Durability | Lost on crash | Survives crashes |
| Visibility | Invisible | Tasks visible in Conductor UI |
| Retry efficiency | Re-executes entire workflow | Loop iteration only |
| `start()` / `stream()` | Skipped | Works automatically |
| Human escalation | Not possible | HumanTask with full state |
| Parallel guardrails | Sequential only | ForkTask parallelism |
| Audit / timeout / retry policy | None / hardcoded | Full history; per-task config |
| LLM guardrails | Needs litellm | Uses server LLM providers |

The API is backward-compatible: the `@guardrail` decorator, `OnFail`/`Position` enums, external guardrails, and the new failure modes layer on without breaking existing code. What changes is internal — output guardrails compile into the loop, `LLMGuardrail` becomes an `LlmChatComplete` task, `human` becomes a HumanTask, retry becomes a SetVariable, and `start()`/`stream()` get guardrail support for free.

---

## 4. Recipes / examples

### PII detection with retry

```python
import re
from conductor.ai.agents import Agent, Guardrail, GuardrailResult

def no_pii(content: str) -> GuardrailResult:
    patterns = {
        "credit card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    }
    for name, pat in patterns.items():
        if re.search(pat, content):
            return GuardrailResult(passed=False,
                                   message=f"Response contains {name}. Redact all PII.")
    return GuardrailResult(passed=True)

agent = Agent(name="safe_agent", model="openai/gpt-4o", tools=[...],
              guardrails=[Guardrail(no_pii, on_fail="retry", max_retries=3)])
```

### Automatic redaction with fix

```python
import re
from conductor.ai.agents import Agent, Guardrail, GuardrailResult

def redact_all_pii(content: str) -> GuardrailResult:
    patterns = [
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "XXXX-XXXX-XXXX-XXXX"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "XXX-XX-XXXX"),
        (r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL REDACTED]"),
    ]
    fixed, found = content, False
    for pat, replacement in patterns:
        if re.search(pat, fixed):
            found = True
            fixed = re.sub(pat, replacement, fixed)
    if found:
        return GuardrailResult(passed=False, message="PII redacted.", fixed_output=fixed)
    return GuardrailResult(passed=True)

agent = Agent(name="redacting_agent", model="openai/gpt-4o", tools=[...],
              guardrails=[Guardrail(redact_all_pii, on_fail="fix")])
```

### JSON-only output enforcement

```python
from conductor.ai.agents import Agent, RegexGuardrail

agent = Agent(
    name="json_agent", model="openai/gpt-4o",
    instructions="Always respond with valid JSON.",
    guardrails=[RegexGuardrail(
        patterns=[r"^\s*[\{\[]"], mode="allow", name="json_only",
        message="Response must start with { or [. Output only valid JSON.",
        on_fail="retry",
    )],
)
```

### Layered guardrails (lenient + strict)

```python
from conductor.ai.agents import Agent, Guardrail, GuardrailResult, RegexGuardrail

length_guard = Guardrail(
    lambda c: GuardrailResult(passed=len(c) <= 1000, message="Too long. Be concise."),
    on_fail="retry", name="length_check",
)
ssn_guard = RegexGuardrail(patterns=[r"\b\d{3}-\d{2}-\d{4}\b"], on_fail="raise", name="no_ssn")

agent = Agent(name="layered_agent", model="openai/gpt-4o", tools=[...],
              guardrails=[length_guard, ssn_guard])
# Guardrails run in order. The first failure determines the action.
```

### Compliance review with human escalation

```python
from conductor.ai.agents import Agent, Guardrail, GuardrailResult

def compliance_check(content: str) -> GuardrailResult:
    flagged = ["guaranteed returns", "risk-free", "investment advice"]
    for term in flagged:
        if term.lower() in content.lower():
            return GuardrailResult(passed=False,
                message=f"Contains flagged term: '{term}'. Requires compliance review.")
    return GuardrailResult(passed=True)

agent = Agent(name="finance_agent", model="openai/gpt-4o", tools=[...],
              guardrails=[Guardrail(compliance_check, on_fail="human", name="compliance")])

# Use start() since the execution may pause (see §2.2 for the poll/approve loop)
with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Should I invest in tech stocks?")
```

### SQL injection blocking on a tool

```python
import re
from conductor.ai.agents import Guardrail, GuardrailResult, tool

def no_sql_injection(content: str) -> GuardrailResult:
    dangerous = [r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--", r"UNION\s+SELECT"]
    for pat in dangerous:
        if re.search(pat, content, re.IGNORECASE):
            return GuardrailResult(passed=False, message=f"Blocked: {pat}")
    return GuardrailResult(passed=True)

@tool(guardrails=[Guardrail(no_sql_injection, position="input", on_fail="raise")])
def run_query(query: str) -> str:
    """Execute a database query."""
    return f"Results: {query}"  # never called with a dangerous query
```

### Tool output sanitization (redact secrets)

```python
import re
from conductor.ai.agents import Guardrail, GuardrailResult, tool

def redact_secrets(content: str) -> GuardrailResult:
    pattern = r"sk-[a-zA-Z0-9]{40,}"
    if re.search(pattern, content):
        return GuardrailResult(passed=False, message="API key redacted.",
                               fixed_output=re.sub(pattern, "sk-***REDACTED***", content))
    return GuardrailResult(passed=True)

@tool(guardrails=[Guardrail(redact_secrets, position="output", on_fail="fix")])
def fetch_config(service: str) -> str:
    return '{"api_key": "sk-abc123def456ghi789jkl012mno345pqr678stu901"}'
# The tool result has the API key redacted before the LLM sees it
```

---

## 5. Background & rationale

*Condensed from an industry review of OpenAI Agents SDK, AG2 (AutoGen), LangGraph/LangChain, CrewAI, Guardrails AI, and NVIDIA NeMo Guardrails, and a gap analysis of our own implementation.*

### Why guardrails matter for agents, not just LLMs

For a single LLM call, guardrails are useful; for **agents** they are essential, because autonomy amplifies risk:

- Agents make multi-step decisions without human oversight, and each tool call is an **action** (email, DB write, API call), not just text.
- A single bad decision cascades through tool chains; a 25-turn agent has far more surface area than one prompt/response.
- The **Swiss-cheese model** applies: no single guardrail catches everything, so effective safety means defense in depth across multiple checkpoints.

| Surface | LLM risk | Agent risk (amplified) |
|---------|----------|------------------------|
| Prompt injection | LLM follows injected instructions | Agent executes injected tool calls |
| Data exfiltration | LLM mentions sensitive data | Agent sends sensitive data via tools |
| Hallucination | Wrong text | Wrong actions from hallucinated reasoning |
| Loop exploitation | N/A | Infinite tool-call loop, burning tokens |

Guardrails span six concern layers — Safety (toxic content), Security (injection, exfiltration), Compliance (PII, HIPAA/GDPR), Quality (hallucination, format), Policy (brand/tone), and Cost (token/loop guards).

### Failure-mode patterns across the industry

The industry has converged on five patterns; our `on_fail` modes implement four of them directly, and route-to-agent is expressible via multi-agent strategies:

- **Tripwire** (OpenAI) — raise and halt → our `raise`.
- **Retry with feedback** (Orkes/CrewAI) — append feedback, re-run → our `retry`.
- **Route/redirect** (AG2) — hand off to a safety agent.
- **Fix/modify** (Guardrails AI) — auto-correct and continue → our `fix`.
- **Human escalation** — pause for review → our `human`, backed by Conductor's HumanTask.

### How the industry does it — SDK comparison

| Aspect | OpenAI | AG2 | LangGraph | CrewAI | Guardrails AI | NeMo |
|--------|--------|-----|-----------|--------|---------------|------|
| Architecture | Parallel/blocking modes | Event-driven actors | Middleware hooks | Task-level | Composable validators | Flow DSL (Colang) |
| Input | Yes | Yes | Before hooks | Limited | Yes | Yes |
| Output | Yes | Yes | After hooks | Yes | Yes | Yes |
| Tool | Yes | Limited | Wrap hooks | Tool-call hooks | Limited | Execution rails |
| Failure mode | Tripwire only | Message routing | Raise/modify | Retry/error | exception/fix/retry/custom | Event blocking |
| Unique feature | Parallel mode | Agent routing | 5 lifecycle hooks | Hallucination guard | Validator hub (100+) | Colang DSL |

Takeaways: OpenAI's parallel-vs-blocking execution is a genuine latency innovation but offers only tripwire; LangGraph's five lifecycle hooks are the most flexible but unopinionated; Guardrails AI has the best composability but isn't agent-aware; CrewAI's hallucination guardrail is a useful domain-specific type; NeMo's Colang is the most expressive but adds a language to learn. Most SDKs cover only input/output (checkpoints 1 and 5) — the agent-critical checkpoints 3 (post-model) and 4 (tool) are where only OpenAI and LangGraph have meaningful coverage.

### Our differentiator and the gap analysis that drove this design

Our key advantage is **server-side durable execution via Conductor**. Two capabilities follow that no other SDK has:

- **Durable, assignable, auditable human-in-the-loop escalation** (`on_fail="human"`) via HumanTask, with assignment, form templates, and timeout policies — surviving process restarts.
- **Loop-internal retry** that costs one DoWhile iteration instead of a full re-execution.

The original implementation ran guardrails **client-side in Python**, which contradicted that advantage: checks were skipped if the client crashed, invisible in the UI, re-submitted the entire execution on retry, and were unavailable to `start()`/`stream()`. A `compile_guardrail_tasks()` method existed but was never wired in. This design closes those gaps in phases:

1. **Core server-side guardrails** — wire compilation into the DoWhile loop; support `retry` (SetVariable + continue) and `raise` (TerminateTask); configurable `max_retries`; remove client-side output logic.
2. **New failure modes** — `human` (HumanTask), `fix` (corrected output), and `LLMGuardrail` as a server-side `LlmChatComplete`.
3. **Tool guardrails** — `@tool(guardrails=[...])`, pre/post compilation, DynamicFork integration.
4. **Advanced** — parallel guardrails via ForkTask, composable `&`/`|` operators, and built-in types (`PIIGuardrail`, `ToxicityGuardrail`, `PromptInjectionGuardrail`, `HallucinationGuardrail`), plus pass/fail and retry-cost metrics surfaced in the Conductor UI.

The resulting recommended architecture keeps **input guardrails client-side** (one-shot, no durability benefit) and compiles **output and tool guardrails into the workflow** (durable, visible, efficient retry, human escalation) — see the loop diagrams in §3.
