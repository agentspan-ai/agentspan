# Agents

`Agent` is the single orchestration primitive. One agent wraps an LLM plus tools. An agent whose tools include other agents is a multi-agent system — no separate Team or Swarm classes.

## Builder

```java
Agent agent = Agent.builder()
    .name("my_agent")                          // required; becomes the Conductor workflow name
    .model("openai/gpt-4o-mini")               // required; "provider/model" format
    .instructions("You are a helpful agent.")  // system prompt
    .build();
```

Every field below is optional.

### @AgentDef annotation

Instead of the builder, a method can be annotated with `@AgentDef` (the Java counterpart of the Python SDK's `@agent` decorator). The method body returns the instructions; `@Tool` and `@GuardrailDef` methods on the same object are attached automatically.

```java
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.annotations.AgentDef;
import org.conductoross.conductor.ai.annotations.Tool;

public class Weather {
    @Tool(name = "get_weather", description = "Get weather for a city")
    public String getWeather(String city) { return "Sunny, 72F in " + city; }

    @AgentDef(model = "openai/gpt-4o")
    public String weatherbot() {
        return "You are a weather assistant.";
    }
}

Agent agent = Agent.fromInstance(new Weather(), "weatherbot");
```

| Attribute | Default | Description |
|---|---|---|
| `name` | method name | Agent name. |
| `model` | `""` | `"provider/model"`. When empty and used as a sub-agent, inherits the parent's model. |
| `instructions` | `""` | Static system prompt. A non-empty `String` returned by the method wins over this attribute. |
| `tools` | `{"*"}` | Names of `@Tool` methods on the same object. `{"*"}` = all, `{}` = none. |
| `guardrails` | `{"*"}` | Names of `@GuardrailDef` methods on the same object. Same wildcard rules. |
| `agents` | `{}` | Names of other `@AgentDef` methods on the same object, used as sub-agents. |
| `strategy` | `HANDOFF` | Multi-agent strategy. |
| `maxTurns` | `25` | Maximum agent loop iterations. |
| `maxTokens` | unset | LLM `max_tokens` (`0` = unset). |
| `temperature` | unset | Sampling temperature (`NaN` = unset). |
| `credentials` | `{}` | Agent-level credential names. |
| `contextWindowBudget` | unset | Proactive condensation threshold (`0` = unset). |

**Method contract.** The return type declares what the method provides:

| Return type | Meaning |
|---|---|
| `void` | Nothing — the annotation attributes alone define the agent. |
| `String` | Dynamic instructions. A no-arg method is **lazy**: re-invoked on every run submission (when the config is serialized), so the prompt can reflect current state. A non-empty result wins over the `instructions` attribute. |
| `PromptTemplate` | Server-side instructions template (`instructionsTemplate`); invoked once. |
| `Agent.Builder` | The definition itself — the returned builder is built. |
| `Agent` | The definition itself, returned as-is (full factory, CrewAI-style). |

The method may take no parameters, or a single `Agent.Builder` parameter — the escape hatch to the full builder API. The builder arrives pre-populated from the annotation and the discovered tools/guardrails/sub-agents; the method body can then apply anything the builder supports, including sub-agents defined in other classes. Builder-param methods are invoked exactly once (a customizer must not be replayed per run):

```java
public class Research {
    @AgentDef(model = "openai/gpt-4o", instructions = "You are a researcher.")
    public void researcher(Agent.Builder builder) {
        builder.termination(new MaxMessageTermination(10))
               .agents(Agent.fromInstance(new Editing(), "editor"));
    }

    // full factory — annotation is a discovery marker; attributes other than name are rejected
    @AgentDef
    public Agent reviewer() {
        return Agent.builder().name("reviewer").model("openai/gpt-4o")
                .instructions("Review the draft.").build();
    }
}
```

`Agent.fromInstance(obj)` resolves all `@AgentDef` methods on an object; `Agent.fromInstance(obj, "name")` resolves one. For factory methods the lookup name is still the annotation `name`/method name, while the agent keeps the name the factory set.

Dynamic instructions are also available directly on the builder, without the annotation: `Agent.builder().instructions(() -> "Today is " + LocalDate.now())` — the supplier is re-evaluated on each run submission, matching the Python SDK's callable instructions.

**Discovery rules.** `@AgentDef` methods must be `public` (a non-public annotated method throws rather than being silently ignored) and cannot also carry `@Tool` or `@GuardrailDef`. Discovery walks the full type hierarchy — superclasses and interfaces (including `default` methods) — and the nearest annotated declaration wins. An unannotated override does *not* hide the agent: the ancestor's annotation is used and invocation dispatches to the override, so CGLIB-proxied Spring beans (`@Transactional` etc.) keep working. In Spring Boot apps, the auto-configured [`AgentCatalog`](../spring-boot.md) collects `@AgentDef` agents from every bean.

### Identity

| Builder method | Type | Default | Description |
|---|---|---|---|
| `name(String)` | `String` | — | **Required.** Unique workflow name. Use `snake_case`. |
| `model(String)` | `String` | — | **Required.** `"provider/model"`, e.g. `"openai/gpt-4o"`, `"anthropic/claude-opus-4-8"`. |
| `instructions(String)` | `String` | `""` | System prompt. |
| `instructionsTemplate(PromptTemplate)` | `PromptTemplate` | `null` | Prompt stored on the server; use `PromptTemplate.of("name")`. |
| `introduction(String)` | `String` | `null` | Injected before the first user message (not the system prompt). |
| `metadata(Map<String,Object>)` | `Map` | `{}` | Arbitrary key-value metadata stored with the workflow. |

### LLM tuning

| Builder method | Type | Default | Description |
|---|---|---|---|
| `maxTurns(int)` | `int` | `25` | Maximum agent loop iterations before termination. |
| `maxTokens(int)` | `int` | `null` | LLM `max_tokens`. |
| `temperature(double)` | `double` | `null` | LLM sampling temperature. |
| `thinkingBudgetTokens(int)` | `int` | `null` | Extended thinking budget (Anthropic only). |
| `timeoutSeconds(int)` | `int` | `0` | Overall agent execution timeout. `0` lets the server apply its own default. |

### Tools

```java
import org.conductoross.conductor.ai.internal.ToolRegistry;

Agent agent = Agent.builder()
    .name("tool_agent")
    .model("openai/gpt-4o-mini")
    .tools(ToolRegistry.fromInstance(new MyTools()))          // from @Tool-annotated POJO
    .tools(HttpTool.builder()
        .name("search")
        .url("https://api.example.com/search")
        .method("GET").build())                    // HTTP tool
    .build();
```

See [Tools](tools.md) for all tool types.

### Multi-agent

```java
Agent pipeline = writer.then(editor);             // .then() = Strategy.SEQUENTIAL shorthand

Agent team = Agent.builder()
    .name("team")
    .model("openai/gpt-4o-mini")
    .agents(writer, editor, reviewer)
    .strategy(Strategy.PARALLEL)
    .build();
```

See [Multi-Agent](multi-agent.md) for all strategies.

### Guardrails

```java
import org.conductoross.conductor.ai.guardrail.RegexGuardrail;
import org.conductoross.conductor.ai.guardrail.LLMGuardrail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.enums.OnFail;

Agent agent = Agent.builder()
    .name("safe_agent")
    .model("openai/gpt-4o-mini")
    .guardrails(
        RegexGuardrail.builder()
            .name("no_phone").position(Position.OUTPUT)
            .patterns("\\d{10}").onFail(OnFail.RAISE).build(),
        LLMGuardrail.builder()
            .name("tone_check").position(Position.OUTPUT)
            .model("openai/gpt-4o-mini").policy("The tone must be professional.")
            .onFail(OnFail.RETRY).build())
    .build();
```

See [Guardrails](guardrails.md).

### Credentials

Declare which secrets the agent's tools require. The SDK fetches them from the Agentspan secrets store at runtime and injects them into tool context.

```java
Agent agent = Agent.builder()
    .name("github_agent")
    .model("openai/gpt-4o-mini")
    .credentials("GITHUB_TOKEN", "JIRA_API_KEY")
    .build();

// In the tool:
public String createIssue(String title, ToolContext ctx) {
    String token = Credentials.get("GITHUB_TOKEN");
    // ...
}
```

### Code execution

```java
Agent agent = Agent.builder()
    .name("coder")
    .model("openai/gpt-4o-mini")
    .localCodeExecution(true)
    .allowedLanguages(List.of("python", "javascript"))
    .codeExecutionTimeout(30)          // seconds per execution
    .build();
```

### Callbacks

Intercept the agent loop before or after each model call:

```java
Agent agent = Agent.builder()
    .name("observed_agent")
    .model("openai/gpt-4o-mini")
    .beforeModelCallback(ctx -> {
        System.out.println("Calling LLM with: " + ctx.get("messages"));
        return ctx;  // return modified context or the original
    })
    .afterModelCallback(ctx -> {
        System.out.println("LLM replied: " + ctx.get("output"));
        return ctx;
    })
    .build();
```

### Fallback

Run a second agent if the first exceeds `fallbackMaxTurns`:

```java
Agent agent = Agent.builder()
    .name("primary")
    .model("openai/gpt-4o-mini")
    .fallback(Agent.builder().name("backup").model("anthropic/claude-haiku-4-5-20251001").build())
    .fallbackMaxTurns(5)
    .build();
```

---

## Running an agent

### AgentRuntime

`AgentRuntime` is the SDK entry point. Use try-with-resources — `close()` stops worker threads and releases HTTP connections.

```java
try (AgentRuntime runtime = new AgentRuntime()) {
    AgentResult result = runtime.run(agent, "Hello!");
}
```

| Method | Returns | Description |
|---|---|---|
| `run(agent, prompt)` | `AgentResult` | Blocking — waits for completion. |
| `run(agent, prompt, plan)` | `AgentResult` | Blocking with a deterministic plan. |
| `runAsync(agent, prompt)` | `CompletableFuture<AgentResult>` | Non-blocking. |
| `start(agent, prompt)` | `AgentHandle` | Fire-and-forget; returns a handle to poll or approve. |
| `startAsync(agent, prompt)` | `CompletableFuture<AgentHandle>` | Non-blocking start. |
| `stream(agent, prompt)` | `AgentStream` | Blocking iterator over events. |
| `streamAsync(agent, prompt)` | `CompletableFuture<AgentStream>` | Non-blocking stream. |
| `plan(agent)` | `CompileResponse` | Compile only — returns `getWorkflowDef()` + `getRequiredWorkers()` without executing. |
| `deploy(Agent...)` | `List<DeploymentInfo>` | Register workflow definitions without running them. |
| `serve(Agent...)` | `void` | Long-running worker mode — keeps polling indefinitely. |
| `resume(executionId, agent)` | `AgentHandle` | Resume a suspended execution. |
| `schedules()` | `Schedules` | Access the scheduling API. |

### AgentResult

```java
AgentResult result = runtime.run(agent, "prompt");

result.getOutput();          // Object — final LLM output (String or structured object)
result.getStatus();          // AgentStatus.COMPLETED / FAILED / TERMINATED / TIMED_OUT
result.getExecutionId();     // String — Conductor workflow ID
result.getToolCalls();       // List<Map<String,Object>> — all tool invocations
result.getEvents();          // List<AgentEvent> — full event log
result.getTokenUsage();      // TokenUsage — prompt/completion/total tokens
result.isSuccess();          // true if status == COMPLETED
result.getError();           // String — error message if failed
```

### AgentHandle

Returned by `start()` — lets you poll, approve, or stream after the fact:

```java
AgentHandle handle = runtime.start(agent, "prompt");
String executionId = handle.getExecutionId();

// Poll until done (blocks the calling thread)
AgentResult result = handle.waitForResult();

// Or approve a human-in-the-loop step
handle.approve("Looks good");
handle.reject("Not acceptable");
```

### Concurrency

`AgentRuntime` is thread-safe. Share one instance across threads rather than creating one per request.

```java
// Good — one shared runtime
private static final AgentRuntime runtime = new AgentRuntime();

// Run multiple agents concurrently
List<CompletableFuture<AgentResult>> futures = prompts.stream()
    .map(p -> runtime.runAsync(agent, p))
    .toList();
CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();
```
