# Callbacks

Callbacks let you observe or intercept the agent loop. Each callback runs as a local Conductor
worker, so the function executes in your JVM while the workflow drives it. A callback returns:

- an empty map (or `null`) to pass through unchanged, or
- a non-empty map to override the value at that point in the loop.

There are two styles: composable `CallbackHandler` instances (recommended) and single-function
builder callbacks.

## CallbackHandler

Subclass `CallbackHandler` and override only the hooks you need. Register one or more handlers with
`.callbacks(...)`; they run in list order and the first non-empty return short-circuits.

```java
import org.conductoross.conductor.ai.CallbackHandler;
import java.util.Map;

public class LoggingHandler extends CallbackHandler {
    @Override
    public Map<String,Object> onModelStart(Map<String,Object> kwargs) {
        System.out.println("→ LLM call: " + kwargs.get("messages"));
        return Map.of();          // pass through
    }

    @Override
    public Map<String,Object> onToolStart(Map<String,Object> kwargs) {
        System.out.println("→ tool: " + kwargs);
        return Map.of();
    }
}

Agent agent = Agent.builder()
    .name("observed_agent")
    .model("anthropic/claude-sonnet-4-6")
    .callbacks(new LoggingHandler())
    .build();
```

### Hooks

| Method | Fires | Worker task |
|---|---|---|
| `onAgentStart(Map)` | Before the agent's execution begins | `{name}_before_agent` |
| `onAgentEnd(Map)` | After the agent's execution finishes | `{name}_after_agent` |
| `onModelStart(Map)` | Before each LLM call | `{name}_before_model` |
| `onModelEnd(Map)` | After each LLM call | `{name}_after_model` |
| `onToolStart(Map)` | Before each tool call | `{name}_before_tool` |
| `onToolEnd(Map)` | After each tool call | `{name}_after_tool` |

Each method takes a `Map<String,Object>` and returns a `Map<String,Object>`. Only overridden
methods are registered as workers.

## Function-style callbacks

For one-off hooks without a class, use the function-typed builder methods. Each takes a
`Function<Map<String,Object>, Map<String,Object>>`:

```java
Agent agent = Agent.builder()
    .name("observed_agent")
    .model("anthropic/claude-sonnet-4-6")
    .beforeModelCallback(ctx -> { System.out.println("calling LLM: " + ctx.get("messages")); return ctx; })
    .afterModelCallback(ctx -> { System.out.println("LLM replied: " + ctx.get("output")); return ctx; })
    .beforeAgentCallback(ctx -> ctx)
    .afterAgentCallback(ctx -> ctx)
    .build();
```

Both styles serialize into a single `callbacks` list on the wire — the function objects are never
sent; each becomes a Conductor task reference and the runtime registers your function as a local
worker.
