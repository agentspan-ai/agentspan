# Guardrails

Guardrails validate or modify agent input and output. They run before the agent sees a message (`INPUT`) or after the agent produces a response (`OUTPUT`).

There are several kinds, each producing a `GuardrailDef`:

- `RegexGuardrail.builder()` — pattern matching (`guardrailType="regex"`)
- `LLMGuardrail.builder()` — LLM-judged policy (`guardrailType="llm"`)
- `GuardrailDef.builder().func(...)` — a custom Java function (`guardrailType="custom"`)
- `Guardrail.of(name, func)` — shorthand builder for a custom Java function
- `Guardrail.external(name)` — reference an existing Conductor worker as a guardrail

## Quick example

```java
import org.conductoross.conductor.ai.guardrail.RegexGuardrail;
import org.conductoross.conductor.ai.guardrail.LLMGuardrail;
import org.conductoross.conductor.ai.enums.OnFail;
import org.conductoross.conductor.ai.enums.Position;

Agent agent = Agent.builder()
    .name("safe_agent")
    .model("anthropic/claude-sonnet-4-6")
    .guardrails(
        // Block output containing a phone-number pattern
        RegexGuardrail.builder()
            .name("no_phone_numbers")
            .position(Position.OUTPUT)
            .patterns("\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b")
            .onFail(OnFail.RAISE)
            .build(),

        // Ask an LLM to enforce a policy; retry the turn if it fails
        LLMGuardrail.builder()
            .name("professional_tone")
            .position(Position.OUTPUT)
            .model("anthropic/claude-sonnet-4-6")
            .policy("The response must be professional and free of slang.")
            .onFail(OnFail.RETRY)
            .build())
    .build();
```

## Guardrail types

### Regex — `RegexGuardrail`

Match one or more patterns against the content.

```java
RegexGuardrail.builder()
    .name("no_secrets")
    .position(Position.OUTPUT)
    .patterns("password", "secret", "api[_-]?key")   // varargs or List<String>
    .message("Output blocked: contained a secret")    // optional
    .onFail(OnFail.RAISE)
    .build();
```

### LLM — `LLMGuardrail`

Ask a language model to evaluate the content against a policy.

```java
LLMGuardrail.builder()
    .name("safe_content")
    .position(Position.OUTPUT)
    .model("anthropic/claude-sonnet-4-6")
    .policy("Reject any harmful, offensive, or unsafe content.")
    .onFail(OnFail.RAISE)
    .build();
```

### Custom — `GuardrailDef.builder().func(...)`

Provide a `Function<String, GuardrailResult>` for full control. Runs as a local Conductor worker.

```java
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.GuardrailResult;

GuardrailDef.builder()
    .name("length_check")
    .position(Position.OUTPUT)
    .func(content -> {
        if (content.length() > 5000) {
            return GuardrailResult.fail("Response too long: " + content.length() + " chars");
        }
        return GuardrailResult.pass();
    })
    .onFail(OnFail.RAISE)
    .build();
```

## Common builder options

| Method | Available on | Default | Description |
|---|---|---|---|
| `name(String)` | all | **required** | Guardrail ID. |
| `position(Position)` | all | `OUTPUT` | `INPUT` or `OUTPUT`. |
| `onFail(OnFail)` | all | `RAISE` | Action when the guardrail fails. |
| `maxRetries(int)` | all | `3` | Retry budget when `onFail == RETRY`. |
| `patterns(String...)` / `patterns(List<String>)` | `RegexGuardrail` | — | Regex patterns to match. |
| `mode(String)` | `RegexGuardrail` | `"block"` | `"block"` fails on a match; `"allow"` fails when nothing matches. |
| `message(String)` | `RegexGuardrail` | — | Custom failure message. |
| `model(String)` | `LLMGuardrail` | — | Judge model, `"provider/model"`. |
| `policy(String)` | `LLMGuardrail` | — | Policy the content must satisfy. |
| `func(Function<String,GuardrailResult>)` | `GuardrailDef` | — | The check, for custom guardrails. |

## Positions

| Constant | When it runs |
|---|---|
| `Position.INPUT` | Before the user message reaches the agent's LLM |
| `Position.OUTPUT` | After the agent produces a response, before it's returned |

## OnFail actions

| Constant | Effect |
|---|---|
| `OnFail.RAISE` | Terminate the agent run with an error (default) |
| `OnFail.RETRY` | Re-run the LLM turn, up to `maxRetries` times |
| `OnFail.FIX` | Replace the output with the guardrail's fixed output (custom guardrails return it via `GuardrailResult.fix(...)`); falls back to `RAISE` if none is provided |
| `OnFail.HUMAN` | Pause for human review (HITL) |

## GuardrailResult

Custom (`func`) guardrails return `GuardrailResult`:

```java
GuardrailResult.pass()                         // guardrail passed
GuardrailResult.fail("reason")                 // guardrail failed
GuardrailResult.fix("rewritten output")        // provide a fixed replacement
```
