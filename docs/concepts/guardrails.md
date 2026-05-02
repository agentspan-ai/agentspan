---
title: Guardrails
description: Input and output validation — custom functions, regex, LLM judges, four on_fail modes
---

# Guardrails

Guardrails validate agent input or output. On failure, you choose how to respond: retry with feedback, raise an error, auto-fix, or escalate to a human.

## Import

```python
from agentspan.agents import (
    Agent, AgentRuntime, Guardrail, GuardrailResult, guardrail,
    OnFail, Position, RegexGuardrail, LLMGuardrail,
)
```

## Basic Usage

```python
from agentspan.agents import Agent, AgentRuntime, Guardrail, GuardrailResult, guardrail

@guardrail
def word_limit(content: str) -> GuardrailResult:
    """Keep responses concise."""
    if len(content.split()) > 500:
        return GuardrailResult(passed=False, message="Too long. Be more concise.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="concise_bot",
    model="openai/gpt-4o",
    guardrails=[Guardrail(word_limit, on_fail=OnFail.RETRY)],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Explain quantum computing.")
    result.print_result()
```

## GuardrailResult

```python
GuardrailResult(
    passed: bool,                            # True if content passes
    message: str = "",                       # Feedback for the LLM on retry
    fixed_output: Optional[str] = None,      # Corrected output for on_fail="fix"
)
```

## OnFail Modes

| Mode | Behavior |
|---|---|
| `OnFail.RETRY` | Append feedback message and re-run the LLM (up to `max_retries` times) |
| `OnFail.RAISE` | Fail the execution immediately |
| `OnFail.FIX` | Replace output with `GuardrailResult.fixed_output` |
| `OnFail.HUMAN` | Pause for human review (creates a WaitTask) |

String values (`"retry"`, `"raise"`, `"fix"`, `"human"`) also work.

## Guardrail Constructor

```python
Guardrail(
    func: Optional[Callable[[str], GuardrailResult]] = None,
    position: Union[str, Position] = Position.OUTPUT,   # "input" or "output"
    on_fail: Union[str, OnFail] = OnFail.RETRY,
    name: Optional[str] = None,
    max_retries: int = 3,
)
```

## Position

```python
class Position(str, Enum):
    INPUT  = "input"    # Run before the LLM call (validate the user's prompt)
    OUTPUT = "output"   # Run after the LLM call (validate the response)
```

## Custom Guardrail

```python
@guardrail
def no_pii(content: str) -> GuardrailResult:
    """Reject responses containing email addresses."""
    import re
    if re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content):
        return GuardrailResult(passed=False, message="Response contains PII (email). Remove it.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[Guardrail(no_pii, on_fail=OnFail.RETRY, max_retries=3)],
)
```

## RegexGuardrail

Block or allow responses based on regex patterns:

```python
from agentspan.agents import RegexGuardrail

# Block responses containing profanity
agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[
        RegexGuardrail(patterns=r"\b(badword1|badword2)\b", mode="block", on_fail=OnFail.RETRY),
    ],
)

# Only allow responses matching a pattern
agent = Agent(
    name="structured_bot",
    model="openai/gpt-4o",
    guardrails=[
        RegexGuardrail(patterns=r"^\d{4}-\d{2}-\d{2}$", mode="allow", on_fail=OnFail.RETRY),
    ],
)
```

## LLMGuardrail

Use a second LLM as a judge:

```python
from agentspan.agents import LLMGuardrail

factual_check = LLMGuardrail(
    model="openai/gpt-4o-mini",
    policy="Is this response factually accurate and helpful? Reply YES or NO with a brief explanation.",
    on_fail=OnFail.RETRY,
    max_retries=2,
)

agent = Agent(
    name="research_bot",
    model="openai/gpt-4o",
    guardrails=[factual_check],
)
```

## Input Guardrails

Validate the user's prompt before it reaches the LLM:

```python
@guardrail
def no_jailbreak(content: str) -> GuardrailResult:
    """Block jailbreak attempts."""
    red_flags = ["ignore previous instructions", "act as", "jailbreak"]
    if any(flag in content.lower() for flag in red_flags):
        return GuardrailResult(passed=False, message="Request blocked.")
    return GuardrailResult(passed=True)

agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[Guardrail(no_jailbreak, position=Position.INPUT, on_fail=OnFail.RAISE)],
)
```

## Auto-Fix

Use `OnFail.FIX` to replace the output automatically:

```python
@guardrail
def ensure_json(content: str) -> GuardrailResult:
    """Ensure the output is valid JSON."""
    import json
    try:
        json.loads(content)
        return GuardrailResult(passed=True)
    except json.JSONDecodeError:
        return GuardrailResult(
            passed=False,
            message="Output must be valid JSON.",
            fixed_output='{"error": "Could not generate valid JSON"}',
        )

agent = Agent(
    name="json_bot",
    model="openai/gpt-4o",
    guardrails=[Guardrail(ensure_json, on_fail=OnFail.FIX)],
)
```

## Multiple Guardrails

Chain multiple guardrails — they run in order:

```python
agent = Agent(
    name="safe_bot",
    model="openai/gpt-4o",
    guardrails=[
        Guardrail(no_jailbreak, position=Position.INPUT, on_fail=OnFail.RAISE),
        Guardrail(no_pii, on_fail=OnFail.RETRY, max_retries=3),
        Guardrail(word_limit, on_fail=OnFail.RETRY),
    ],
)
```
