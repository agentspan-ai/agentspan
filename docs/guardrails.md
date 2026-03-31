# Guardrails for AI Agents — Conceptual Analysis & SDK Review

## Context

Deep analysis of what guardrails are, why they matter, when/where they execute, and how they should be implemented for agent systems. Reviews AG2, OpenAI Agents SDK, LangGraph, CrewAI, Guardrails AI, and NVIDIA NeMo. Evaluates the Orkes Conductor Agents SDK's current guardrail implementation against the industry state-of-the-art.

---

## 1. What Are Guardrails?

Guardrails are **validation and safety boundaries** that constrain an AI agent's behavior at defined checkpoints. They are NOT just content filters — they are a fundamental architectural pattern for making agents trustworthy in production.

A guardrail answers one question: **"Should this content be allowed to proceed?"**

The answer is one of:
- **Pass** — content is acceptable, continue
- **Fail** — content violates a policy, take corrective action
- **Fix** — content has issues but can be automatically corrected

### Taxonomy of Guardrail Concerns

| Layer | What it protects | Examples |
|-------|-----------------|----------|
| **Safety** | Users from harmful content | Toxic language, self-harm, violence |
| **Security** | System from attacks | Prompt injection, jailbreaking, data exfiltration |
| **Compliance** | Organization from liability | PII leakage (SSNs, credit cards), HIPAA/GDPR violations |
| **Quality** | Users from bad output | Hallucinations, off-topic responses, format errors |
| **Policy** | Business from brand risk | Competitor mentions, unauthorized claims, tone violations |
| **Cost** | Budget from runaway usage | Token limits, loop guards, expensive tool call prevention |

---

## 2. Why Guardrails Matter for Agents (Not Just LLMs)

For a single LLM call, guardrails are useful. For **agents**, they are **essential**. Here's why:

### Agents amplify risk through autonomy
- Agents make multi-step decisions without human oversight
- Each tool call is an **action** (not just text) — sending emails, writing to databases, making API calls
- A single bad decision can cascade through tool chains
- An agent running for 25 turns with tools has exponentially more surface area than a single prompt/response

### The "Swiss cheese model" applies
Like aviation safety, no single guardrail catches everything. Effective agent safety requires **defense in depth** — multiple guardrails at multiple checkpoints, where the holes in one layer are covered by the next.

### Agents have unique attack surfaces
| Surface | LLM risk | Agent risk (amplified) |
|---------|----------|----------------------|
| Prompt injection | LLM follows injected instructions | Agent executes injected tool calls |
| Data exfiltration | LLM mentions sensitive data | Agent sends sensitive data via tools |
| Hallucination | Wrong text response | Agent takes wrong actions based on hallucinated reasoning |
| Loop exploitation | N/A | Agent stuck in infinite tool-call loop, burning tokens |

---

## 3. When & Where Guardrails Execute (The Five Checkpoints)

The agent execution loop has **five natural checkpoints** where guardrails can intercept:

```
User Input
    |
    v
+-------------------+
| 1. INPUT RAILS    | <-- Validate user prompt before any processing
+--------+----------+
         |
    +----v----+
    | LLM Call| <--- 2. PRE-MODEL RAILS (modify/validate prompt to LLM)
    +----+----+
         |
    +----v-----------+
    | 3. POST-MODEL   | <-- Validate LLM response (before tool execution)
    |    RAILS        |
    +----+-----------+
         |
    +----v-----------+
    | Tool Execution  | <--- 4. TOOL RAILS (validate tool inputs/outputs)
    +----+-----------+
         |
    (loop back to LLM or...)
         |
    +----v-----------+
    | 5. OUTPUT RAILS | <-- Validate final response before returning to user
    +----+-----------+
         |
         v
    User Response
```

### Checkpoint details

| # | Checkpoint | When | What it catches | Cost of failure |
|---|-----------|------|-----------------|-----------------|
| 1 | **Input** | Before agent loop starts | Prompt injection, malformed input, off-topic requests | Low (no work done yet) |
| 2 | **Pre-model** | Before each LLM call in the loop | Conversation context poisoning, accumulated injection | Medium |
| 3 | **Post-model** | After LLM responds, before tool dispatch | Hallucinated tool calls, unsafe reasoning | High (about to act) |
| 4 | **Tool** | Around each tool execution | Dangerous parameters, sensitive data in args/results | Critical (action taken) |
| 5 | **Output** | Before returning final answer to user | PII in response, policy violations, quality issues | Medium (no action, just text) |

### The key insight: Checkpoint 3 and 4 are the most critical for agents

Most SDKs only implement checkpoints 1 and 5 (input/output). But for agents, the highest risk is at checkpoints 3 (the LLM decided to call a dangerous tool) and 4 (the tool is about to execute with bad parameters). This is where **tool guardrails** come in — a concept only OpenAI and LangGraph have properly addressed.

---

## 4. How Guardrails Work — Failure Mode Patterns

When a guardrail fails, the system must decide what to do. The industry has converged on five patterns:

### 4a. Tripwire (OpenAI pattern)
```
Guardrail fails -> Raise exception -> Halt execution entirely
```
- **Best for**: Security violations, compliance hard stops
- **Trade-off**: No recovery, but guaranteed safety
- **OpenAI calls this**: `tripwire_triggered = True`

### 4b. Retry with feedback (Orkes/CrewAI pattern)
```
Guardrail fails -> Append feedback to prompt -> Re-run LLM
```
- **Best for**: Quality issues, format problems, soft policy violations
- **Trade-off**: Costs extra tokens, but LLM can self-correct
- **Our SDK does this**: Append `"[Previous response was rejected: {feedback}]"` and retry

### 4c. Route/redirect (AG2 pattern)
```
Guardrail fails -> Route to specialized handler agent
```
- **Best for**: Multi-agent systems where a "safety agent" can handle violations
- **Trade-off**: More complex orchestration
- **AG2 calls this**: "traffic light" with activation message + target agent

### 4d. Fix/modify (Guardrails AI pattern)
```
Guardrail fails -> Auto-correct the content -> Continue with fixed version
```
- **Best for**: Deterministic fixes (redact PII, fix JSON format)
- **Trade-off**: May alter meaning, but fast and non-disruptive
- **Guardrails AI does this**: `on_fail=OnFailAction.FIX`

### 4e. Human escalation
```
Guardrail fails -> Pause execution -> Wait for human review
```
- **Best for**: High-stakes decisions, ambiguous violations
- **Trade-off**: Blocks execution, requires human availability
- **Orkes advantage**: Conductor's HumanTask makes this trivial

---

## 5. Architecture & Design

Guardrails validate agent input/output and take corrective action on failure. They compile into Conductor workflow tasks positioned before (input) or after (output) the LLM call, providing durable, server-side validation that survives process restarts.

### Overview

```
User Prompt
    │
    ├─ [Input Guardrails]        ← validate before LLM sees the prompt
    │
    ├─ LLM Call
    │
    ├─ [Output Guardrails]       ← validate LLM response
    │     │
    │     ├─ pass  → return result
    │     ├─ retry → feedback appended to conversation, LLM retries
    │     ├─ fix   → use corrected output, skip LLM retry
    │     ├─ raise → terminate execution with error
    │     └─ human → pause for human review (approve/edit/reject)
    │
    └─ [Tool Guardrails]         ← validate tool inputs/outputs (Python-level)
```

---

## 6. Guardrail Types

### Custom Function Guardrail

Write a Python function that validates content and returns `GuardrailResult`.

```python
from agentspan.agents import Guardrail, GuardrailResult, guardrail

@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses containing credit card numbers."""
    if re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", content):
        return GuardrailResult(
            passed=False,
            message="Contains PII. Redact all card numbers before responding.",
        )
    return GuardrailResult(passed=True)

agent = Agent(
    ...,
    guardrails=[
        Guardrail(no_pii, position="output", on_fail="retry", max_retries=3),
    ],
)
```

**Compilation:** Compiles to a Conductor **worker task**. The `@guardrail` function runs in the SDK's worker process. Multiple custom guardrails are batched into a single combined worker task — the first failure halts evaluation.

**Output path:** `${ref}.output.*` (direct).

### RegexGuardrail

Pattern-based validation. Runs entirely server-side as a JavaScript InlineTask — no Python worker needed.

```python
from agentspan.agents import RegexGuardrail, OnFail, Position

# Block mode: fail if any pattern matches (blocklist)
no_emails = RegexGuardrail(
    patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
    mode="block",
    name="no_email_addresses",
    message="Response must not contain email addresses.",
    position=Position.OUTPUT,
    on_fail=OnFail.RETRY,
)

# Allow mode: fail if NO pattern matches (allowlist)
json_only = RegexGuardrail(
    patterns=[r"^\s*[\{\[]"],
    mode="allow",
    name="json_output",
    message="Response must be valid JSON.",
)
```

**Compilation:** Compiles to a Conductor **InlineTask** with JavaScript regex evaluation (GraalVM). Patterns, mode, on_fail, message, and max_retries are baked into the script at compile time.

**Output path:** `${ref}.output.result.*` (InlineTask wraps under `.result`).

### LLMGuardrail

Uses a second LLM to evaluate content against a policy. The evaluator LLM receives the policy + content and returns `{"passed": true/false, "reason": "..."}`.

```python
from agentspan.agents import LLMGuardrail

safety = LLMGuardrail(
    model="openai/gpt-4o-mini",
    policy=(
        "Reject any content that:\n"
        "1. Contains medical or legal advice presented as fact\n"
        "2. Makes promises or guarantees about outcomes\n"
        "3. Includes discriminatory or biased language"
    ),
    name="content_safety",
    position="output",
    on_fail="retry",
    max_tokens=10000,
)
```

**Compilation:** Compiles to a **LlmChatComplete** task (evaluator call) followed by an **InlineTask** (response parser). The parser extracts `passed` and `reason` from the LLM's JSON response and maps the on_fail logic.

**Output path:** `${ref}.output.result.*` (InlineTask).

**Note:** Use a fast, small model for the evaluator to avoid slowing down the agent loop.

### External Guardrail

Reference a guardrail worker running elsewhere. No local function — just the name.

```python
# Reference a guardrail deployed as a remote worker
agent = Agent(
    ...,
    guardrails=[
        Guardrail(name="compliance_check", position="output", on_fail="retry"),
    ],
)
```

**Compilation:** Compiles to a Conductor **SimpleTask** referencing the remote worker by name.

**Worker contract:**
- Input: `{"content": "<text>", "iteration": <n>}`
- Output: `{"passed": bool, "message": str, "on_fail": str, "should_continue": bool}`

**Output path:** `${ref}.output.*` (direct).

---

## 7. Failure Modes (on_fail)

| Mode | Behavior | Use Case |
|------|----------|----------|
| `"retry"` | Feedback message appended to conversation. LLM retries with the feedback. After `max_retries` exhausted, escalates to `"raise"`. | Style issues, format corrections — let the LLM fix it. |
| `"fix"` | Uses `GuardrailResult.fixed_output` directly. No LLM retry. | Deterministic fixes (PII redaction, truncation, formatting). Faster and cheaper than retry. |
| `"raise"` | Terminates the execution with `FAILED` status and the guardrail message. | Hard blocks — content that must never pass through. |
| `"human"` | Pauses the execution at a HumanTask. Human can approve, edit, or reject. Only valid for `position="output"`. | Compliance review, sensitive content that needs human judgment. |

### Retry Escalation

When `on_fail="retry"` and the DoWhile loop iteration reaches `max_retries`, the guardrail automatically escalates to `"raise"`. This prevents infinite retry loops.

### Fix Mode

The `fixed_output` field in `GuardrailResult` provides the corrected output:

```python
@guardrail
def redact_phones(content: str) -> GuardrailResult:
    phone_pattern = r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    if re.search(phone_pattern, content):
        redacted = re.sub(phone_pattern, "[PHONE REDACTED]", content)
        return GuardrailResult(
            passed=False,
            message="Phone numbers detected and redacted.",
            fixed_output=redacted,
        )
    return GuardrailResult(passed=True)

agent = Agent(
    ...,
    guardrails=[Guardrail(redact_phones, on_fail="fix")],
)
```

### Human Mode

When `on_fail="human"`, the execution pauses at a HumanTask. Use `start()` (async) since `run()` would block:

```python
handle = runtime.start(agent, "...")

# Poll until waiting
status = handle.get_status()
if status.is_waiting:
    runtime.approve(handle.execution_id)    # approve as-is
    # or: runtime.reject(handle.execution_id, "reason")
    # or: runtime.respond(handle.execution_id, {"edited_output": "..."})
```

The human review flow compiles to:

```
HumanTask → validate → [normalize if needed] → route
  ├─ approve: continue with original output
  ├─ edit: continue with edited output
  └─ reject: terminate execution (FAILED)
```

---

## 8. Position: Input vs Output

| Position | When it runs | Compilation | Scope |
|----------|-------------|-------------|-------|
| `"output"` | After each LLM response, inside the DoWhile loop | Compiled as Conductor workflow tasks (durable, visible in UI) | Agent-level guardrails |
| `"input"` | Before tool execution | Python-level wrapping inside the tool worker (not a separate workflow task) | Tool-level guardrails only |

**Note:** `on_fail="human"` is only valid for `position="output"` — input guardrails run inside Python and cannot pause an execution.

---

## 9. Tool Guardrails

Guardrails can be attached directly to tools for pre/post-execution validation:

```python
sql_guard = Guardrail(
    no_sql_injection,
    position="input",     # check BEFORE tool executes
    on_fail="raise",      # hard block
)

@tool(guardrails=[sql_guard])
def run_query(query: str) -> str:
    """Execute a database query."""
    ...
```

Tool guardrails run inside the tool worker process (Python-level wrapping, not Conductor workflow tasks). The `make_tool_worker()` dispatch wrapper:

1. **Pre-execution** (position="input"): Serializes tool kwargs to JSON, runs guardrail check. On failure with `on_fail="raise"`, raises `ValueError`. Otherwise returns `{error: ..., blocked: True}`.

2. **Post-execution** (position="output"): Serializes tool result, runs guardrail check. On failure with `on_fail="fix"`, replaces result with `fixed_output`. With `on_fail="raise"`, raises `ValueError`.

---

## 10. Standalone Guardrails

`@guardrail`-decorated functions are plain callables — usable without an agent or server:

```python
@guardrail
def no_pii(content: str) -> GuardrailResult:
    ...

# Call directly
result = no_pii("Some text to validate")
print(result.passed, result.message)
```

They can also be deployed as standalone Conductor workers (see example 35), allowing any agent in any language to reference them by name.

---

## 11. Compilation Details

### Where Guardrails Appear in the Workflow

Output guardrails are compiled inside the DoWhile loop, after the LLM task:

```
DoWhile Loop
  ├─ LLM_CHAT_COMPLETE
  ├─ [Guardrail Check Task]           ← evaluates content
  ├─ [Guardrail Routing SwitchTask]   ← acts on result
  ├─ Tool Router (if agent has tools)
  └─ ...
```

### Guardrail Routing SwitchTask

After each guardrail check task, a SwitchTask routes based on `on_fail`:

```
SwitchTask
  expression: ${guardrail_ref}.output[.result].on_fail
  │
  ├─ "pass" (default): SetVariable (no-op, continue)
  │
  ├─ "retry": InlineTask formats feedback
  │    → "[Output validation failed: {message}]"
  │    → wired to LLM as user message for next iteration
  │
  ├─ "raise": TerminateTask (FAILED)
  │
  ├─ "fix": InlineTask passes fixed_output through
  │
  └─ "human": HumanTask → validate → normalize → route
       ├─ approve: continue
       ├─ edit: use edited output
       └─ reject: TerminateTask
```

### Termination Condition Integration

When output guardrails with `on_fail="retry"` exist, their `should_continue` flag is ANDed into the DoWhile termination condition:

```javascript
iteration < max_turns
  && finishReason != 'LENGTH'
  && (toolCalls != null || guardrail_should_continue)
```

This ensures the loop continues when a guardrail signals retry.

### Output Path Differences

The SwitchTask must read from different paths depending on guardrail type:

| Guardrail Type | Output Path |
|----------------|-------------|
| RegexGuardrail (InlineTask) | `$.{ref}.result.on_fail` |
| LLMGuardrail (InlineTask) | `$.{ref}.result.on_fail` |
| Custom function (Worker) | `$.{ref}.on_fail` |
| External (SimpleTask) | `$.{ref}.on_fail` |

This is tracked via the `is_inline` flag returned by `_compile_output_guardrail_tasks()`.

---

## 12. Multi-Agent Guardrail Wrapping

When a multi-agent strategy workflow has output guardrails, the entire strategy workflow is wrapped in an outer DoWhile loop:

```
DoWhile (guardrail_loop)
  ├─ InlineSubWorkflow (strategy workflow)
  ├─ [Guardrail Check Task(s)]
  └─ [Guardrail Routing SwitchTask(s)]
```

This re-runs the full strategy workflow on retry.

---

## 13. How the Industry Does It — SDK Comparison

### OpenAI Agents SDK
**Key innovation: Parallel execution + tripwire**
- Guardrails can run **concurrently with the LLM** (default) — optimizes latency
- Or **blocking mode** — prevents token waste if guardrail will fail
- Tripwire pattern: binary pass/fail, raises typed exception
- Three positions: input, output, and **tool guardrails** (unique)
- Guardrail function receives full `context + agent + input/output` — rich context

**Strength**: Execution control (parallel vs blocking) is a genuine innovation
**Weakness**: Only tripwire failure mode (no retry/fix)

### AG2 (AutoGen)
**Key innovation: Route-to-agent pattern**
- Guardrails are event-driven, fit the actor model
- When triggered, redirects conversation to a specialized agent
- Two types: regex (fast/deterministic) and LLM (semantic)
- "Activation message" concept — custom message shown when guardrail triggers

**Strength**: Multi-agent routing is natural for multi-agent frameworks
**Weakness**: No retry or fix modes, only redirect

### LangGraph / LangChain
**Key innovation: Middleware hooks at 5 lifecycle points**
- `before_agent`, `after_agent`, `before_model`, `after_model`, `wrap_tool_call`
- Familiar middleware pattern from web frameworks
- Class-based middleware can carry state across hooks
- Built-in PII detection with multiple strategies (redact, mask, hash, block)

**Strength**: Most flexible — hooks at every point in the lifecycle
**Weakness**: No opinionated guardrail type system — too low-level

### CrewAI
**Key innovation: Hallucination guardrail**
- 5-step validation: context comparison -> faithfulness scoring -> verdict -> threshold -> feedback
- Task-level integration (guardrails on tasks, not agents)
- Generates detailed feedback with scoring for retry

**Strength**: Domain-specific guardrail types (hallucination detection is genuinely useful)
**Weakness**: Limited to output position, no input/tool guardrails

### Guardrails AI (standalone library)
**Key innovation: Composable validator pipeline**
- `Guard().use(Validator1(), Validator2(), ...)` — chain validators
- Pre-built validator hub (100+ validators)
- Four failure modes: exception, fix, retry, custom handler
- Each validator is independent, reusable, testable

**Strength**: Best composability model — validators are true building blocks
**Weakness**: Not agent-aware — doesn't understand tools, loops, or handoffs

### NVIDIA NeMo Guardrails
**Key innovation: Domain-specific language (Colang)**
- Dedicated programming language for defining guardrail flows
- Five rail types: input, retrieval, dialog, execution, output
- Event-driven state machine
- Dialog rails control conversation flow (unique)

**Strength**: Most expressive — can model complex conversational guardrail logic
**Weakness**: High learning curve, another language to maintain

### Comparison Table

| Aspect | OpenAI | AG2 | LangGraph | CrewAI | Guardrails AI | NeMo |
|--------|--------|-----|-----------|--------|---------------|------|
| **Architecture** | Parallel/Blocking modes | Event-driven actors | Middleware hooks | Task-level | Composable validators | Flow-based DSL |
| **Input Guardrails** | Yes (blocking/parallel) | Yes (pre-agent) | Before hooks | Limited | Yes (Guard wrapper) | Yes (input rails) |
| **Output Guardrails** | Yes (explicit) | Yes (post-agent) | After hooks | Yes (task-level) | Yes (Guard wrapper) | Yes (output rails) |
| **Tool Guardrails** | Yes (explicit) | Limited | Wrap hooks | Tool call hooks | Limited | Execution rails |
| **Failure Mode** | Tripwire exception | Message routing | Raise/Modify | Retry/Error | on_fail policies | Event blocking |
| **Composability** | Sequential | Dual-mechanism | Middleware chaining | Per-task | Validator chaining | Flow composition |
| **Unique Feature** | Parallel mode | Agent routing | Middleware patterns | Hallucination guard | Validator hub | Colang DSL |

---

## 14. Our Current Implementation — Honest Assessment

### What we have today

| Aspect | Current State | Assessment |
|--------|--------------|------------|
| **Input guardrails** | Client-side, pre-execution, raise-only | Functional but limited |
| **Output guardrails** | Client-side, post-execution, retry/raise | Functional but wasteful |
| **Tool guardrails** | Not implemented | **Gap** |
| **Guardrail types** | Guardrail, RegexGuardrail, LLMGuardrail + `@guardrail` decorator | Good coverage |
| **Failure modes** | retry, raise, fix, human (`OnFail` enum) | ~~Missing: fix, tripwire, redirect, human~~ Implemented |
| **Composability** | None (sequential list only) | **Gap** vs Guardrails AI |
| **Execution model** | Sequential, client-side | Missing: parallel, server-side |
| **Durability** | Not durable (client-side) | **Fundamental gap** for Conductor |
| **In-loop integration** | Not compiled into workflow | `compile_guardrail_tasks()` exists but unused |
| **Retry limit** | Hardcoded 3 | Should be configurable |
| **Streaming support** | None | `stream()` skips guardrails |
| **Fire-and-forget** | `start()` skips guardrails | **Gap** |

### The fundamental architectural issue

Our guardrails run **client-side in the Python process**, but our key differentiator is **server-side durable execution via Conductor**. This means:

1. If the client crashes after the execution completes but before guardrail checking, guardrails are skipped
2. Guardrails are invisible in the Conductor UI (no task, no status, no logs)
3. Output guardrail retry re-submits the **entire execution** instead of repeating just the LLM call inside the DoWhile loop
4. `start()` (fire-and-forget) and `stream()` can't run output guardrails at all

The `compile_guardrail_tasks()` method in `agent_compiler.py` was clearly the intended design — compile guardrails as worker tasks inside the workflow — but it was never wired in.

### What we do well

1. **Three guardrail types** (custom, regex, LLM) — matches industry standard
2. **Retry with feedback** — genuinely useful, most SDKs only have tripwire/halt
3. **Position-based** (input/output) — clean API
4. **`on_fail` parameter** — configurable failure behavior per guardrail
5. **GuardrailResult with message** — feedback flows back to LLM for self-correction

---

## 15. Gaps & Recommendations

### Tier 1: Critical gaps (should fix)

**15a. Compile output guardrails into the DoWhile loop**
- Output guardrails should be worker tasks INSIDE the agent loop
- After the LLM responds and before the next iteration, check guardrails
- If guardrail fails with `retry`: append feedback to messages and continue the loop (no full re-execution)
- If guardrail fails with `raise`: terminate the execution with an error
- This makes guardrails **durable** and **visible in Conductor UI**
- The `compile_guardrail_tasks()` method is the starting point

**15b. Add tool guardrails (Checkpoint 4)**
- Allow `@tool(guardrails=[...])` or a new `ToolGuardrail` type
- Validate tool inputs before execution (e.g., block SQL injection in query params)
- Validate tool outputs after execution (e.g., redact PII from API responses)
- This is the highest-risk checkpoint for agents and only OpenAI/LangGraph address it

**15c. Make retry limit configurable**
- `Guardrail(func, on_fail="retry", max_retries=5)`
- Currently hardcoded to 3 in runtime.py

### Tier 2: Important enhancements

**15d. Add `on_fail="fix"` mode**
- Guardrail returns corrected content instead of just pass/fail
- `GuardrailResult(passed=False, message="...", fixed_output="corrected text")`
- Runtime uses `fixed_output` instead of retrying — faster, cheaper
- Useful for deterministic corrections (PII redaction, format fixing)

**15e. Add `on_fail="human"` mode**
- Guardrail failure pauses execution via Conductor HumanTask
- Human reviews and approves/rejects/edits
- Natural fit for Conductor's existing human-in-the-loop support
- Major differentiator — no other SDK has durable human escalation for guardrails

**15f. Composable guardrails with `&` / `|`**
- `guardrail_a & guardrail_b` -> both must pass
- `guardrail_a | guardrail_b` -> either can pass
- Same pattern as our TerminationCondition composability

**15g. Support guardrails in `start()` and `stream()`**
- Since guardrails will be compiled into the Conductor workflow, they'll automatically work with all execution modes
- This is a natural consequence of fixing 15a

### Tier 3: Nice-to-have

**15h. Parallel execution mode (OpenAI-style)**
- Run guardrails concurrently with the LLM call
- If guardrail fails, cancel/discard the LLM response
- Optimization for latency-sensitive applications

**15i. Built-in guardrail types**
- `PromptInjectionGuardrail` — detect common injection patterns
- `PIIGuardrail` — detect PII with multiple strategies (block, redact, mask)
- `HallucinationGuardrail` — fact-check against provided context (CrewAI-style)
- `ToxicityGuardrail` — content safety classification

**15j. Guardrail metrics/observability**
- Track pass/fail rates per guardrail
- Track retry counts and costs
- Surface in Conductor UI dashboard

---

## 16. Recommended Architecture

```
User Input
    |
    v
[Input Guardrails]          <-- Client-side (fast, pre-execution)
    |                          Positions: "input"
    |                          Modes: raise, human
    v
+-- DoWhile Loop ------------------------------------------+
|                                                          |
|   [LLM Call]                                            |
|       |                                                  |
|       v                                                  |
|   [Output Guardrails]     <-- Server-side worker tasks  |
|       |                      Positions: "output"         |
|       |                      Modes: retry, raise, fix,   |
|       |                              human               |
|       v                                                  |
|   [Tool Dispatch]                                       |
|       |                                                  |
|       v                                                  |
|   [Tool Guardrails]       <-- Server-side, per-tool     |
|       |                      Positions: "tool_input",    |
|       |                                 "tool_output"    |
|       v                                                  |
|   (next iteration or exit)                              |
|                                                          |
+----------------------------------------------------------+
    |
    v
Final Output
```

### Key architectural decisions
1. **Input guardrails stay client-side** — they run once, before the execution, and don't need durability
2. **Output guardrails compile into the DoWhile loop** — durable, visible, efficient retry
3. **Tool guardrails are new** — wrap individual tool executions, highest-risk checkpoint
4. **`on_fail="human"`** leverages Conductor's HumanTask — unique differentiator
5. **`on_fail="fix"`** enables auto-correction without retry — faster and cheaper
