# Stateful Agents — Task-to-Domain Routing

## Problem

When multiple concurrent instances of the same agent script run simultaneously
(e.g. two users opening the chat REPL at the same time), all instances register
their `@tool`-decorated workers under the same Conductor task name and default
domain.  Conductor can route a task dispatched by instance A to instance B's
worker, silently mixing results across sessions.

## Solution

Mark tools — or a whole agent — as **stateful**.  At execution time:

1. The Python SDK generates a unique `run_id` (UUID hex) for the execution.
2. Stateful tool workers are registered under `domain=run_id` so they only poll
   tasks belonging to their own execution.
3. The server sets `taskToDomain` on `StartWorkflowRequest` so Conductor routes
   stateful tasks exclusively to the run-specific workers.

Non-stateful tools (HTTP, MCP, or `@tool` without `stateful=True` on a
non-stateful agent) are unaffected — they continue to use the default domain.

## API

Two equivalent ways to opt in:

```python
# Option A — per-tool (only those tools get domain-isolated)
@tool(stateful=True)
def reply_to_user(message: str) -> str: ...

@tool(stateful=True)
def run_task(task_name: str, task_input: str) -> str: ...

agent = Agent(name="chat_repl_agent", tools=[..., reply_to_user, run_task])

# Option B — whole agent (all worker tools get domain-isolated)
@tool
def reply_to_user(message: str) -> str: ...

agent = Agent(name="chat_repl_agent", tools=[..., reply_to_user], stateful=True)
```

Both produce the same outcome: a `run_id` is generated, matching workers poll
that domain, and the server routes those tasks there.

## When to use

Use `stateful=True` on long-running agents that may run concurrently and whose
worker tools carry per-execution state (filesystem IPC, in-memory registries,
session-specific callbacks).  Short-lived one-shot agents are unaffected because
they complete before a second instance would overlap.

The WMQ-based examples (`75`–`82`) are the canonical cases: each is designed to
run indefinitely and may have multiple concurrent sessions.

## Implementation

### Python SDK

| File | Change |
|---|---|
| `agents/tool.py` | `ToolDef.stateful: bool = False`; `@tool(stateful=True)` parameter |
| `agents/agent.py` | `Agent(stateful=True)` parameter |
| `agents/runtime/runtime.py` | `_has_stateful_tools(agent)` checks `agent.stateful OR any td.stateful`; generates `run_id` when true |
| `agents/runtime/tool_registry.py` | Registers worker with `domain` if `agent_stateful OR td.stateful` |
| `agents/config_serializer.py` | Emits `"stateful": true` on tool JSON if `agent.stateful OR td.stateful` |

### Server (Java)

| File | Change |
|---|---|
| `model/ToolConfig.java` | `boolean stateful` field |
| `model/StartRequest.java` | `String runId` field |
| `service/AgentService.java` | `collectWorkerToolNames` routes tools where `tool.isStateful()` to the `runId` domain; uses per-tool names (not `"*"`) so system tasks like `LLM_CHAT_COMPLETE` are unaffected |
