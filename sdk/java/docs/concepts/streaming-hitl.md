# Streaming & Human-in-the-Loop

## Streaming events

`runtime.stream(agent, prompt)` returns an `AgentStream` — an `Iterable<AgentEvent>` (and
`AutoCloseable`) that yields events over server-sent events as the agent runs. After iteration,
`getResult()` returns the completed `AgentResult`.

```java
import org.conductoross.conductor.ai.enums.EventType;

try (AgentStream stream = runtime.stream(agent, "Tell me a story")) {
    for (AgentEvent event : stream) {
        switch (event.getType()) {
            case MESSAGE     -> System.out.print(event.getContent());
            case TOOL_CALL   -> System.out.println("→ " + event.getToolName() + " " + event.getArgs());
            case TOOL_RESULT -> System.out.println("← " + event.getResult());
            case DONE        -> { /* stream ended */ }
            default          -> {}
        }
    }
    AgentResult result = stream.getResult();
}
```

### Event types

`EventType`: `THINKING`, `TOOL_CALL`, `TOOL_RESULT`, `HANDOFF`, `WAITING`, `MESSAGE`, `ERROR`,
`DONE`, `GUARDRAIL_PASS`, `GUARDRAIL_FAIL`.

`AgentEvent` accessors: `getType()`, `getContent()`, `getToolName()`, `getArgs()`, `getResult()`,
`getOutput()`, `getExecutionId()`, `getGuardrailName()`, `getPendingToolCalls()`.

## Human-in-the-loop

An agent pauses for a human whenever it hits a HITL gate. Two common ways to create one:

- A tool marked `@Tool(approvalRequired = true)` — the agent pauses before executing it.
- A `HumanTool` the LLM can call to ask a person directly (see [Tools](tools.md#human-in-the-loop-tools)).

A guardrail with `onFail(OnFail.HUMAN)` also pauses for review.

### Approving via a handle

`runtime.start(...)` returns an `AgentHandle` you can drive from anywhere — the workflow stays
parked durably in Conductor in the meantime (seconds or days).

```java
AgentHandle handle = runtime.start(agent, "Deploy v2.1 to production");

handle.waitUntilWaiting(60_000);     // block until a HITL task is paused (optional)
if (handle.isWaiting()) {
    handle.approve("Approved by Alice");   // or handle.approve()
    // handle.reject("Needs more testing");
    // handle.respond(Map.of("selected", "writer"));   // arbitrary payload (e.g. MANUAL strategy)
}

AgentResult result = handle.waitForResult();
```

| Method | Wire payload |
|---|---|
| `approve()` | `{ "approved": true }` |
| `approve(comment)` | `{ "approved": true, "reason": comment }` |
| `reject(reason)` | `{ "approved": false, "reason": reason }` |
| `respond(map)` | the map, at the top level |

### Approving from a stream

While streaming, watch for `WAITING` events and approve inline. Use the **event-targeted**
overloads — `approve(event)` / `reject(event, reason)` — so approvals for a sub-agent's execution
route to the right execution (the top-level `approve()` targets the root workflow only).

```java
for (AgentEvent event : stream) {
    if (event.getType() == EventType.WAITING) {
        System.out.println("Approval needed for: " + event.getToolName());
        stream.approve(event);                 // targets event.getExecutionId()
        // stream.reject(event, "not allowed");
    }
}
```

`AgentStream` also exposes the top-level `approve()` / `reject(reason)` and a
`send(message)` / `send(event, message)` pair for multi-turn replies to a waiting workflow.
