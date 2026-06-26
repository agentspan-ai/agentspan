# Guardrails — Conductor Implementation Design

How Conductor's workflow primitives map to guardrail patterns, and the concrete compilation design for the Orkes Agents SDK.

---

## 1. Conductor Construct-to-Guardrail Mapping

Conductor already has every building block needed. The question is composition.

| Conductor Construct | Guardrail Role | How it fits |
|-------------------|----------------|-------------|
| **`worker_task`** | Guardrail execution engine | Each guardrail function (custom, regex, LLM) becomes a Conductor worker task. Runs on the worker process, results are durable workflow state. This is what `compile_guardrail_tasks()` already does. |
| **`LlmChatComplete`** | Server-side LLM guardrails | Instead of calling litellm client-side (current `LLMGuardrail`), compile as a Conductor `LlmChatComplete` task. Runs on the server, uses the configured LLM provider, visible in UI. No extra dependencies. |
| **`SwitchTask`** | Failure mode routing | After guardrail worker returns `{passed, message, on_fail}`, a SwitchTask routes: `"retry"` -> append feedback + continue loop, `"raise"` -> TerminateTask, `"fix"` -> use fixed_output, `"human"` -> HumanTask. |
| **`DoWhileTask`** | The agent loop (already exists) | Output guardrails insert into the existing DoWhile body: `[LLM] -> [Guardrail Worker] -> [SwitchTask on result] -> [Tool Dispatch]`. The loop's termination condition already checks `should_continue`. |
| **`HumanTask`** | `on_fail="human"` | When guardrail fails with `on_fail="human"`, insert a HumanTask that shows the violation details. Human approves (continue), rejects (terminate), or edits (use modified output). This is our **unique differentiator** -- no other SDK can do durable human-in-the-loop guardrail escalation. |
| **`TerminateTask`** | `on_fail="raise"` / tripwire | Immediately terminates the workflow with `FAILED` status and the guardrail's failure message as the reason. Clean, durable, visible in Conductor UI. |
| **`SetVariableTask`** | State tracking & feedback injection | When guardrail fails with `retry`: append the feedback message to `workflow.variables.messages` as a system message, then let the DoWhile loop naturally iterate back to the LLM. No full workflow re-execution needed. |
| **`ForkTask`** | Parallel guardrails | Run multiple guardrails simultaneously (PII check + toxicity check + policy check). Join and aggregate. Maps to OpenAI's parallel execution mode but with durable fork/join semantics. |
| **`InlineTask`** | Score aggregation | After parallel guardrails, a JavaScript InlineTask computes the composite risk score and determines whether to pass/fail/escalate. Fast, no worker needed. |
| **`TerminateTask`** | Hard stop / tripwire | Immediately end the workflow on critical violations. |
| **`SubWorkflowTask`** | Modular guardrail chains | Package a guardrail pipeline (e.g., "enterprise compliance chain") as a reusable sub-workflow. Different agents can reference the same guardrail chain. |

---

## 2. Concrete Compilation Pattern: Output Guardrail in the DoWhile Loop

### Current loop structure (native FC path)

```
DoWhile:
  [1. LlmChatComplete]
  [2. SwitchTask (tool_call vs final_answer)]
       -> tool_call: DynamicFork -> merge -> SetVariable(messages)
       -> default: SetVariable(messages)
```

### With guardrails compiled in

```
DoWhile:
  [1. LlmChatComplete]
  [2. Guardrail worker_task]          <-- NEW: checks LLM output
  [3. SwitchTask on guardrail result] <-- NEW: routes on pass/fail
       -> "pass":  [original SwitchTask (tool_call vs final_answer)]
       -> "retry": [SetVariable(append feedback to messages)]  <-- loop continues
       -> "raise": [TerminateTask(FAILED, reason)]
       -> "fix":   [SetVariable(use fixed_output)] -> [original SwitchTask]
       -> "human": [HumanTask] -> [SwitchTask on human decision]
                                    -> approved: continue
                                    -> rejected: TerminateTask
```

The termination condition stays the same -- it already checks `iteration < max_turns && should_continue`. The guardrail just determines whether `should_continue` remains true.

### Key detail: Retry via feedback injection

When `on_fail="retry"`, the guardrail worker returns:
```json
{
  "passed": false,
  "message": "Response contains a credit card number. Redact all PII.",
  "on_fail": "retry",
  "should_continue": true
}
```

The retry path appends feedback to `workflow.variables.messages`:
```python
# SetVariable appends a system message with guardrail feedback
set_retry = SetVariableTask(task_ref_name="guardrail_retry_feedback")
set_retry.input_parameter("messages", [
    ...existing_messages,
    {"role": "system", "message": "[Guardrail: ${guardrail.output.message}. Please revise your response.]"}
])
```

The DoWhile loop naturally iterates back to the LLM, which now sees the feedback and self-corrects. **No full workflow re-execution needed** -- just another loop iteration.

---

## 3. Concrete Compilation Pattern: Tool Guardrails

### Current tool execution (native FC path)

```
SwitchTask (toolCalls present?):
  -> tool_call: DynamicFork(tool workers) -> merge results -> SetVariable(messages)
```

### With tool guardrails

```
SwitchTask (toolCalls present?):
  -> tool_call:
      [Pre-tool guardrail worker]           <-- NEW: validates tool inputs
      [SwitchTask on pre-tool result]        <-- NEW
        -> "pass": DynamicFork(tool workers)
        -> "block": SetVariable(blocked message) -> skip tool
      [Post-tool guardrail worker]           <-- NEW: validates tool outputs
      [SwitchTask on post-tool result]       <-- NEW
        -> "pass": merge results -> SetVariable
        -> "fix":  use sanitized output -> SetVariable
```

### Why tool guardrails matter most

Tool calls are the highest-risk checkpoint because they take **real-world actions**:
- An LLM might hallucinate a `send_email(to="all@company.com", body="...")` call
- A tool might return PII from a database that gets included in subsequent LLM context
- SQL injection in tool parameters could compromise databases

Pre-tool guardrails catch dangerous inputs; post-tool guardrails sanitize dangerous outputs.

---

## 4. Concrete Compilation Pattern: `on_fail="human"` Escalation

```
[Guardrail worker returns {passed: false, on_fail: "human"}]
    |
    v
[HumanTask]
  input: {
    content: "${llm_output}",
    violation: "${guardrail.message}",
    guardrail_name: "pii_check",
    options: ["approve", "reject", "edit"]
  }
    |
    v
[SwitchTask on human decision]
  -> "approve": SetVariable(continue) -> resume loop
  -> "reject":  TerminateTask(FAILED, "Human rejected: {reason}")
  -> "edit":    SetVariable(use human's edited output) -> resume loop
```

This uses Conductor's existing `HumanTask` infrastructure -- assignment to users/groups, form templates, timeout policies. The workflow durably pauses and resumes across process restarts.

### Why this is a unique differentiator

No other agent SDK can do this:
- **OpenAI**: Tripwire only -- halt or continue, no human review
- **AG2**: Redirect to another agent, not a human review queue
- **LangGraph**: Middleware hooks are in-process, not durable
- **CrewAI**: Retry only, no human escalation

Conductor's HumanTask gives us **durable, assignable, auditable human-in-the-loop guardrail escalation** out of the box.

---

## 5. Concrete Compilation Pattern: Parallel Guardrails via ForkTask

```
[LlmChatComplete output]
    |
    v
[ForkTask]
  +-- [PII guardrail worker]
  +-- [Toxicity guardrail worker]
  +-- [Policy guardrail worker]
[JoinTask]
    |
    v
[InlineTask: aggregate results]
  script: "any guardrail failed? -> return worst result"
    |
    v
[SwitchTask on aggregate result]
  -> "pass": continue
  -> "fail": route to appropriate on_fail handler
```

### Aggregation logic (InlineTask JavaScript)

```javascript
(function() {
  var pii = $.pii_guard.output;
  var toxicity = $.toxicity_guard.output;
  var policy = $.policy_guard.output;

  // If any guardrail failed, find the most severe
  var results = [pii, toxicity, policy];
  var failed = results.filter(function(r) { return !r.passed; });

  if (failed.length === 0) {
    return { passed: true, on_fail: "pass" };
  }

  // Priority: raise > human > retry > fix
  var priority = { "raise": 4, "human": 3, "retry": 2, "fix": 1 };
  failed.sort(function(a, b) {
    return (priority[b.on_fail] || 0) - (priority[a.on_fail] || 0);
  });

  return failed[0];  // Return the most severe failure
})()
```

---

## 6. LLM Guardrails: Server-Side vs Client-Side

### Current: Client-side via litellm (LLMGuardrail)

```python
# Current implementation calls litellm from the Python worker process
import litellm
response = litellm.completion(model="openai/gpt-4o-mini", messages=[...])
```

Problems:
- Requires `litellm` dependency
- Runs in the worker process, not on the server
- Not visible in Conductor UI
- No retry/timeout policies from Conductor

### Proposed: Server-side via LlmChatComplete task

```python
# Compiled as a Conductor LlmChatComplete task
guardrail_llm = LlmChatComplete(
    task_ref_name=f"{agent_name}_guardrail_llm",
    llm_provider="openai",           # Uses server-configured provider
    model="gpt-4o-mini",
    messages=[
        ChatMessage(role="system", message=guardrail_policy_prompt),
        ChatMessage(role="user", message="${llm_output}"),
    ],
    temperature=0.0,
    max_tokens=200,
    json_output=True,
)
```

Benefits:
- Uses server-configured LLM providers (no extra keys needed)
- Visible as a task in Conductor UI
- Automatic retry/timeout from Conductor task policies
- No extra Python dependencies
- Can use prompt templates registered in Conductor

### When to use each

| Approach | When to use |
|----------|-------------|
| **worker_task** (custom Python) | Custom guardrails with complex logic, regex, database lookups |
| **LlmChatComplete** (server-side) | LLM-based guardrails -- policy evaluation, content classification |
| **InlineTask** (JavaScript) | Simple checks -- threshold comparison, pattern matching, score aggregation |

---

## 7. Why Compiled Guardrails Are Better Than Client-Side

| Aspect | Client-side (current) | Compiled into workflow |
|--------|----------------------|----------------------|
| **Durability** | Lost on crash | Survives crashes |
| **Visibility** | Invisible | Tasks visible in Conductor UI |
| **Retry efficiency** | Re-executes entire workflow | Loop iteration only |
| **start()/stream()** | Guardrails skipped | Works automatically |
| **Human escalation** | Not possible | HumanTask with full state |
| **Parallel guardrails** | Sequential only | ForkTask parallelism |
| **Audit trail** | None | Full task execution history |
| **Timeout** | No timeout | Conductor task timeout |
| **Retry policy** | Hardcoded 3 | Configurable per-task |
| **LLM guardrails** | Needs litellm dependency | Uses server LLM providers |

---

## 8. What Stays Client-Side

**Input guardrails** should remain client-side because:

1. They run once, before workflow submission -- no durability benefit
2. Fast rejection saves server resources (don't even create the workflow)
3. Simple raise/block semantics don't need workflow orchestration
4. Client-side is actually the right place for prompt validation

Input guardrails continue to work exactly as they do today:
```python
# In runtime.run(), before workflow submission
for guard in agent.guardrails:
    if guard.position == "input":
        result = guard.check(prompt)
        if not result.passed:
            raise ValueError(f"Input guardrail '{guard.name}' failed: {result.message}")
```

---

## 9. API Surface (No Breaking Changes)

The user-facing API is backward-compatible. New additions (`@guardrail` decorator, `OnFail`/`Position` enums, external guardrails) layer on without breaking existing code:

```python
from agentspan.agents import guardrail, Guardrail, GuardrailResult, OnFail, Position

@guardrail
def my_custom_check(content: str) -> GuardrailResult:
    ...

agent = Agent(
    name="safe_agent",
    model="openai/gpt-4o",
    tools=[my_tool],
    guardrails=[
        RegexGuardrail(patterns=[r"\d{3}-\d{2}-\d{4}"], mode="block", on_fail=OnFail.RETRY),
        LLMGuardrail(model="openai/gpt-4o-mini", policy="No PII", on_fail=OnFail.HUMAN),
        Guardrail(my_custom_check, position=Position.OUTPUT, on_fail=OnFail.RAISE),
        Guardrail(name="compliance_checker", on_fail=OnFail.RETRY),  # External guardrail
    ],
)

# Plain strings still work — OnFail and Position are str subclasses
result = runtime.run(agent, "Process this customer request")
```

What changes internally:
- Output guardrails compile as worker tasks inside the DoWhile loop
- LLMGuardrail compiles as a server-side LlmChatComplete task
- `on_fail="human"` compiles as a HumanTask in the guardrail SwitchTask
- Retry appends feedback to messages via SetVariable (loop-internal)
- `start()` and `stream()` automatically get guardrail support

---

## 10. Implementation Priority

### Phase 1: Core server-side guardrails
- Wire `compile_guardrail_tasks()` into the DoWhile loop body
- Support `on_fail="retry"` (SetVariable + loop continue) and `on_fail="raise"` (TerminateTask)
- Make retry limit configurable via `Guardrail(max_retries=N)`
- Remove client-side output guardrail logic from `runtime.run()`

### Phase 2: New failure modes
- Add `on_fail="human"` (HumanTask escalation)
- Add `on_fail="fix"` (use corrected output)
- Compile LLMGuardrail as server-side LlmChatComplete task

### Phase 3: Tool guardrails
- `@tool(guardrails=[...])` parameter
- Pre-tool and post-tool guardrail compilation
- Integration with DynamicFork tool dispatch

### Phase 4: Advanced
- Parallel guardrails via ForkTask
- Composable guardrails with `&` / `|` operators
- Built-in guardrail types (PII, toxicity, prompt injection)
