# Guardrails Guide

Guardrails validate agent inputs and outputs, preventing unsafe, non-compliant, or malformed content from reaching users. They integrate directly into the Conductor workflow so retries, escalations, and fixes are **durable**, **visible in the Conductor UI**, and work with every execution mode (`run()`, `start()`, `stream()`).

---

## Table of Contents

- [Quick Start](#quick-start)
- [How Guardrails Work](#how-guardrails-work)
- [Guardrail Classes](#guardrail-classes)
  - [Guardrail (Custom Function)](#guardrail-custom-function)
  - [RegexGuardrail](#regexguardrail)
  - [LLMGuardrail](#llmguardrail)
- [Failure Modes (on\_fail)](#failure-modes-on_fail)
  - [retry](#retry-default)
  - [raise](#raise)
  - [fix](#fix)
  - [human](#human)
- [Configuring Retries (max\_retries)](#configuring-retries-max_retries)
- [Tool Guardrails](#tool-guardrails)
- [Architecture: Compiled vs. Client-Side](#architecture-compiled-vs-client-side)
- [Recipes](#recipes)
- [API Reference](#api-reference)

---

## Quick Start

```python
import re
from agentspan.agents import (
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

# 4. Run — the guardrail retries automatically inside the workflow
with AgentRuntime() as runtime:
    result = runtime.run(agent, "Show me customer CUST-7's full profile.")
    print(result.output)  # Credit card number will be redacted
```

> **Note:** Plain strings (`"output"`, `"retry"`) still work — `OnFail` and `Position` are `str` enums for discoverability and IDE autocompletion.

---

## How Guardrails Work

A guardrail is a function `(content: str) -> GuardrailResult` that checks content and returns pass/fail. You attach guardrails to an **agent** (for LLM output validation) or to a **tool** (for tool I/O validation).

**The lifecycle:**

1. The LLM generates a response (or a tool produces output).
2. Each guardrail runs against that content in order.
3. On the first failure, the `on_fail` strategy determines what happens:
   - **retry** — feedback is appended to messages and the LLM tries again.
   - **raise** — the execution terminates with `FAILED` status.
   - **fix** — the guardrail's corrected output replaces the original.
   - **human** — the execution pauses for a human to approve, reject, or edit.

For agents with tools, guardrails compile into the Conductor DoWhile loop as real workflow tasks. This means retries happen inside the loop (not by re-executing the entire workflow), and the guardrail check is visible as a task in the Conductor UI.

---

## Guardrail Classes

### Guardrail (Custom Function)

The base class — wrap any Python function as a guardrail.

```python
from agentspan.agents import Guardrail, GuardrailResult

def check_length(content: str) -> GuardrailResult:
    if len(content) > 500:
        return GuardrailResult(passed=False, message="Response too long. Be concise.")
    return GuardrailResult(passed=True)

guard = Guardrail(
    func=check_length,
    position="output",   # "input" or "output"
    on_fail="retry",     # "retry", "raise", "fix", or "human"
    name="length_check", # Optional, defaults to function name
    max_retries=3,       # Max retry attempts (default: 3)
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `func` | `Callable[[str], GuardrailResult]` | *required* | Validation function |
| `position` | `str` | `"output"` | `"input"` (before LLM) or `"output"` (after LLM) |
| `on_fail` | `str` | `"retry"` | `"retry"`, `"raise"`, `"fix"`, or `"human"` |
| `name` | `str` | function name | Human-readable identifier |
| `max_retries` | `int` | `3` | Max retries for `on_fail="retry"` |

### RegexGuardrail

Pattern-based validation — block or require content matching regex patterns.

```python
from agentspan.agents import RegexGuardrail

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

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `patterns` | `str \| List[str]` | *required* | Regex patterns to check |
| `mode` | `str` | `"block"` | `"block"` (reject matches) or `"allow"` (reject non-matches) |
| `message` | `str` | auto-generated | Custom failure message |
| `position` | `str` | `"output"` | `"input"` or `"output"` |
| `on_fail` | `str` | `"retry"` | Failure strategy |
| `max_retries` | `int` | `3` | Max retries |

### LLMGuardrail

Use a second LLM to evaluate content against a written policy.

```python
from agentspan.agents import LLMGuardrail

safety = LLMGuardrail(
    model="openai/gpt-4o-mini",  # Use a fast, cheap model
    policy="Reject any content that provides specific medical diagnoses or prescriptions without a disclaimer.",
    name="medical_safety",
    on_fail="retry",
)
```

The judge LLM receives the content and policy, and responds with `{"passed": true/false, "reason": "..."}`.

> **Note:** Requires the `litellm` package (`pip install litellm`). The guardrail calls the LLM synchronously, so use a fast model to avoid slowing down the agent loop.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | *required* | Model in `"provider/model"` format |
| `policy` | `str` | *required* | Policy description for the judge LLM |
| `position` | `str` | `"output"` | `"input"` or `"output"` |
| `on_fail` | `str` | `"retry"` | Failure strategy |
| `max_retries` | `int` | `3` | Max retries |

---

## Failure Modes (on_fail)

### retry (default)

The LLM gets another chance. Guardrail feedback is appended to the conversation as a user message, and the LLM generates a new response.

```python
Guardrail(no_pii, on_fail="retry", max_retries=3)
```

**What happens:**
1. Guardrail fails → feedback message appended to messages.
2. LLM sees: `[Output validation failed: <message>. Please revise your response.]`
3. LLM generates a new response.
4. Guardrail checks again.
5. Repeats up to `max_retries` times. After that, escalates to `raise`.

**Best for:** Content quality issues the LLM can fix (PII redaction, format compliance, safety).

### raise

The execution terminates immediately with `FAILED` status.

```python
Guardrail(always_block, on_fail="raise")
```

**What happens:**
1. Guardrail fails → execution terminates.
2. `result.status` will be `"FAILED"` or `"TERMINATED"`.
3. The guardrail message is included in the termination reason.

**Best for:** Hard security blocks, zero-tolerance policies, input validation.

### fix

The guardrail provides a corrected version of the output. No LLM retry needed.

```python
import re

def redact_ssn(content: str) -> GuardrailResult:
    pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    if re.search(pattern, content):
        fixed = re.sub(pattern, "XXX-XX-XXXX", content)
        return GuardrailResult(
            passed=False,
            message="SSN detected and redacted.",
            fixed_output=fixed,
        )
    return GuardrailResult(passed=True)

Guardrail(redact_ssn, on_fail="fix")
```

**What happens:**
1. Guardrail fails → `fixed_output` from the `GuardrailResult` replaces the LLM's response.
2. The corrected output becomes the final answer.
3. No LLM retry occurs (the guardrail already fixed it).

**Best for:** Deterministic corrections (regex substitution, sanitization, normalization).

### human

The execution pauses for human review. A human can approve, reject, or edit the response.

```python
Guardrail(compliance_check, on_fail="human")
```

> **Restriction:** `on_fail="human"` only works with `position="output"`. Input guardrails are client-side and cannot pause an execution.

**What happens:**
1. Guardrail fails → a HumanTask is created in Conductor.
2. The execution pauses (`status == "PAUSED"`).
3. A human reviews the output via the Conductor UI or API.
4. Three possible actions:
   - **Approve:** `runtime.approve(execution_id)` — output is accepted as-is.
   - **Reject:** `runtime.reject(execution_id, reason="...")` — execution terminates `FAILED`.
   - **Edit:** `runtime.respond(execution_id, {"edited_output": "..."})` — edited text replaces the output.

**Usage with `start()`:**

```python
with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Give me investment advice.")

    # Poll until the execution pauses
    import time
    while True:
        status = handle.get_status()
        if status.is_waiting:
            print("Paused for human review")
            runtime.approve(handle.execution_id)
            break
        if status.is_complete:
            break
        time.sleep(1)

    # Get final result
    status = handle.get_status()
    print(status.output)
```

**Best for:** Compliance review, content moderation, sensitive decisions.

---

## Configuring Retries (max_retries)

The `max_retries` parameter controls how many times `on_fail="retry"` will attempt before escalating to `on_fail="raise"`.

```python
# Agent retries up to 5 times before failing
Guardrail(check_fn, on_fail="retry", max_retries=5)

# No retries — fail immediately (equivalent to on_fail="raise")
Guardrail(check_fn, on_fail="retry", max_retries=0)
```

The default is `3`. When multiple guardrails are attached to an agent, each guardrail has its own `max_retries` value.

For client-side guardrails (simple agents without tools), the runtime uses the maximum `max_retries` value across all output guardrails.

---

## Tool Guardrails

Guardrails can be attached directly to tools to validate inputs before execution or outputs after execution.

```python
from agentspan.agents import Guardrail, GuardrailResult, tool

# Pre-execution guardrail: check tool inputs
def no_sql_injection(content: str) -> GuardrailResult:
    import re
    if re.search(r"DROP\s+TABLE|DELETE\s+FROM|;\s*--", content, re.IGNORECASE):
        return GuardrailResult(passed=False, message="SQL injection blocked.")
    return GuardrailResult(passed=True)

sql_guard = Guardrail(no_sql_injection, position="input", on_fail="raise")

@tool(guardrails=[sql_guard])
def run_query(query: str) -> str:
    """Execute a database query."""
    return f"Results: {query}"
```

**How tool guardrails work:**

- **`position="input"`**: Runs before the tool function. Receives a JSON string of all input parameters. If the guardrail fails, the tool is not executed.
- **`position="output"`**: Runs after the tool function. Receives the tool's return value as a string. If the guardrail fails with `on_fail="fix"`, the fixed output replaces the tool result.

Tool guardrails execute inside the tool's worker process (Python-level wrapping). They do not add extra Conductor tasks — the check happens within the existing tool worker task.

**Post-execution example (output sanitization):**

```python
def redact_secrets(content: str) -> GuardrailResult:
    import re
    pattern = r"sk-[a-zA-Z0-9]{40,}"
    if re.search(pattern, content):
        fixed = re.sub(pattern, "sk-***REDACTED***", content)
        return GuardrailResult(passed=False, fixed_output=fixed, message="API key redacted.")
    return GuardrailResult(passed=True)

@tool(guardrails=[Guardrail(redact_secrets, position="output", on_fail="fix")])
def fetch_config(service: str) -> str:
    """Fetch service configuration."""
    return '{"api_key": "sk-abc123def456ghi789jkl012mno345pqr678stu901"}'
# The tool result will have the API key redacted before the LLM sees it
```

---

## Architecture: Compiled vs. Client-Side

Guardrails behave differently depending on whether the agent has tools.

### Agents with tools (compiled guardrails)

Output guardrails are compiled into the Conductor DoWhile loop as workflow tasks:

```
DoWhile Loop:
  [LLM Task] → [Guardrail Worker] → [Guardrail Switch] → [Tool Router]
```

- **Guardrail Worker**: A single worker task that runs all output guardrails sequentially. Returns pass/fail, the failure mode, and any fixed output.
- **Guardrail Switch**: A SwitchTask that routes based on the guardrail result to the appropriate handler (retry, raise, fix, or human).
- **Retry**: Appends feedback to messages and continues the loop. The LLM sees the feedback on the next iteration.
- **No full re-execution**: Retries are loop iterations, not new workflow runs.

This means guardrails are:
- **Durable** — retries survive worker restarts.
- **Visible** — each guardrail check appears as a task in the Conductor UI.
- **Compatible** — works with `run()`, `start()`, and `stream()`.

### Simple agents (no tools, client-side)

Without tools there is no DoWhile loop, so output guardrails run client-side in the runtime after each workflow execution:

1. Execute workflow.
2. Check output guardrails.
3. If retry needed, modify the prompt and re-execute the entire workflow.

This is simpler but less efficient (full re-execution per retry).

### Input guardrails (always client-side)

Input guardrails (`position="input"`) always run client-side before the workflow starts. Only `on_fail="raise"` is meaningful for input guardrails — there is no LLM to retry against.

---

## Recipes

### PII detection with retry

```python
import re
from agentspan.agents import Agent, Guardrail, GuardrailResult

def no_pii(content: str) -> GuardrailResult:
    patterns = {
        "credit card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    }
    for name, pat in patterns.items():
        if re.search(pat, content):
            return GuardrailResult(
                passed=False,
                message=f"Response contains {name}. Redact all PII.",
            )
    return GuardrailResult(passed=True)

agent = Agent(
    name="safe_agent",
    model="openai/gpt-4o",
    tools=[...],
    guardrails=[Guardrail(no_pii, on_fail="retry", max_retries=3)],
)
```

### Automatic redaction with fix

```python
import re
from agentspan.agents import Agent, Guardrail, GuardrailResult

def redact_all_pii(content: str) -> GuardrailResult:
    patterns = [
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "XXXX-XXXX-XXXX-XXXX"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "XXX-XX-XXXX"),
        (r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL REDACTED]"),
    ]
    fixed = content
    found = False
    for pat, replacement in patterns:
        if re.search(pat, fixed):
            found = True
            fixed = re.sub(pat, replacement, fixed)
    if found:
        return GuardrailResult(passed=False, message="PII redacted.", fixed_output=fixed)
    return GuardrailResult(passed=True)

agent = Agent(
    name="redacting_agent",
    model="openai/gpt-4o",
    tools=[...],
    guardrails=[Guardrail(redact_all_pii, on_fail="fix")],
)
```

### JSON-only output enforcement

```python
from agentspan.agents import Agent, RegexGuardrail

agent = Agent(
    name="json_agent",
    model="openai/gpt-4o",
    instructions="Always respond with valid JSON.",
    guardrails=[
        RegexGuardrail(
            patterns=[r"^\s*[\{\[]"],
            mode="allow",
            name="json_only",
            message="Response must start with { or [. Output only valid JSON.",
            on_fail="retry",
        ),
    ],
)
```

### Layered guardrails (lenient + strict)

```python
from agentspan.agents import Agent, Guardrail, GuardrailResult, RegexGuardrail

# First guardrail: soft check with retry
length_guard = Guardrail(
    lambda c: GuardrailResult(passed=len(c) <= 1000, message="Too long. Be concise."),
    on_fail="retry",
    name="length_check",
)

# Second guardrail: hard block (no SSNs ever)
ssn_guard = RegexGuardrail(
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
    on_fail="raise",
    name="no_ssn",
)

agent = Agent(
    name="layered_agent",
    model="openai/gpt-4o",
    tools=[...],
    guardrails=[length_guard, ssn_guard],
    # Guardrails run in order. First failure determines the action.
)
```

### Compliance review with human escalation

```python
from agentspan.agents import Agent, Guardrail, GuardrailResult

def compliance_check(content: str) -> GuardrailResult:
    flagged = ["guaranteed returns", "risk-free", "investment advice"]
    for term in flagged:
        if term.lower() in content.lower():
            return GuardrailResult(
                passed=False,
                message=f"Contains flagged term: '{term}'. Requires compliance review.",
            )
    return GuardrailResult(passed=True)

agent = Agent(
    name="finance_agent",
    model="openai/gpt-4o",
    tools=[...],
    guardrails=[
        Guardrail(compliance_check, on_fail="human", name="compliance"),
    ],
)

# Use start() since the execution may pause
with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Should I invest in tech stocks?")
    # ... poll status, approve/reject when waiting ...
```

### SQL injection blocking on a tool

```python
import re
from agentspan.agents import Guardrail, GuardrailResult, tool

def no_sql_injection(content: str) -> GuardrailResult:
    dangerous = [r"DROP\s+TABLE", r"DELETE\s+FROM", r";\s*--", r"UNION\s+SELECT"]
    for pat in dangerous:
        if re.search(pat, content, re.IGNORECASE):
            return GuardrailResult(passed=False, message=f"Blocked: {pat}")
    return GuardrailResult(passed=True)

@tool(guardrails=[Guardrail(no_sql_injection, position="input", on_fail="raise")])
def run_query(query: str) -> str:
    """Execute a database query."""
    # This function will never be called with a dangerous query
    return f"Results: {query}"
```

---

## API Reference

### Enums

```python
class OnFail(str, Enum):
    RETRY = "retry"    # Ask the LLM to try again with feedback
    RAISE = "raise"    # Fail the execution immediately
    FIX   = "fix"      # Use GuardrailResult.fixed_output
    HUMAN = "human"    # Pause for human review (output only)

class Position(str, Enum):
    INPUT  = "input"   # Before the LLM call
    OUTPUT = "output"  # After the LLM call
```

Both are `str` enums — plain strings (`"retry"`, `"output"`) continue to work everywhere.

### GuardrailResult

```python
@dataclass
class GuardrailResult:
    passed: bool                         # True if content passes validation
    message: str = ""                    # Feedback for the LLM (used on retry)
    fixed_output: Optional[str] = None   # Corrected output (used with on_fail="fix")
```

### @guardrail decorator

```python
@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject PII."""
    ...

@guardrail(name="pii_checker")   # Custom name
def no_pii(content: str) -> GuardrailResult: ...
```

The decorator attaches a `_guardrail_def` attribute (a `GuardrailDef` dataclass) and preserves the function as callable. `Guardrail()` auto-detects decorated functions.

### Guardrail

```python
class Guardrail:
    def __init__(
        self,
        func: Optional[Callable[[str], GuardrailResult]] = None,
        position: str = "output",    # Position.INPUT | Position.OUTPUT | "input" | "output"
        on_fail: str = "retry",      # OnFail.RETRY | OnFail.RAISE | ... | "retry" | "raise" | ...
        name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None: ...

    external: bool  # True when func is None (references an external worker)
    def check(self, content: str) -> GuardrailResult: ...
```

**External guardrails** — pass `name` without `func` to reference a guardrail worker running elsewhere:

```python
Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)
```

### RegexGuardrail

```python
class RegexGuardrail(Guardrail):
    def __init__(
        self,
        patterns: Union[str, List[str]],
        *,
        mode: str = "block",         # "block" | "allow"
        position: str = "output",
        on_fail: str = "retry",
        name: Optional[str] = None,
        message: Optional[str] = None,
        max_retries: int = 3,
    ) -> None: ...
```

### LLMGuardrail

```python
class LLMGuardrail(Guardrail):
    def __init__(
        self,
        model: str,                   # "provider/model" format
        policy: str,                  # Natural language policy
        *,
        position: str = "output",
        on_fail: str = "retry",
        name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None: ...
```

### @tool with guardrails

```python
@tool(guardrails=[guard1, guard2])
def my_tool(param: str) -> str:
    ...
```

### Agent with guardrails

```python
Agent(
    name="...",
    model="...",
    guardrails=[guard1, guard2],  # List[Guardrail]
)
```
