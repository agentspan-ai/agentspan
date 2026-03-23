# Real-Time Streaming Design Document

## Overview

The Agent SDK supports real-time streaming of agent execution events from the server to clients. This enables clients to observe LLM thinking, tool calls, guardrail evaluations, human-in-the-loop pauses, and final results as they happen — without polling.

## Protocol Choice: SSE + HTTP POST

**Server → Client:** Server-Sent Events (SSE) over HTTP
**Client → Server:** Standard HTTP POST (for HITL responses only)

### Why SSE over WebSockets

| Concern | SSE | WebSockets |
|---|---|---|
| **Directionality** | Server → client (95% of our traffic) | Full duplex |
| **Infrastructure** | Works with all HTTP proxies, CDNs, load balancers, HTTP/2 | Requires upgrade handshake; many proxies don't support it |
| **Reconnection** | Built-in via `Last-Event-ID` | Manual reconnection logic |
| **Lifecycle** | Simple — HTTP request/response; no ping/pong | Connection upgrade, heartbeat management |
| **Thread model** | Tomcat NIO — no thread per connection | Similar with NIO, but more complex lifecycle |
| **Client → server** | Separate HTTP POST | Same connection |

Agent streaming is 95%+ server-to-client. The only client-to-server interaction is HITL (human approving/rejecting a tool call), which happens at human speed and is perfectly served by a standard POST.

### Scalability

- **Tomcat NIO**: 5,000–10,000 concurrent SSE connections per server instance (no thread per connection).
- **Memory**: Each event buffer ≈ 40 KB (200 events). At 10K concurrent workflows → ~400 MB.
- **Future**: If needed, swap Tomcat for Spring WebFlux + Netty for 50K+ connections per instance. Multi-instance deployments can use sticky sessions by workflow ID or a shared event bus (Redis Streams, Kafka).

## Architecture

```
Python SDK (client)                   Java Runtime (embedded Conductor)
───────────────────                   ────────────────────────────────

POST /api/agent/start          →      compile + register + startWorkflow()
  ← {"workflowId": "abc-123"}            │
                                          ↓
GET /api/agent/stream/abc-123  →      SseEmitter registered in AgentStreamRegistry
  ← SSE: thinking                         │
  ← SSE: tool_call                    AgentEventListener
  ← SSE: tool_result                    (TaskStatusListener +
  ← SSE: guardrail_pass                   WorkflowStatusListener)
  ← SSE: waiting                          │
  ...                                 fires on every Conductor state
  ← SSE: done                        change → converts to AgentSSEEvent
                                      → pushes to SseEmitter
POST /api/agent/abc-123/respond →
  {"approved": true}                  updateTask() on pending HUMAN task
```

**Key insight**: Conductor has `TaskStatusListener` and `WorkflowStatusListener` callback interfaces that fire synchronously on every task/workflow state transition. Zero polling on the server — events arrive the instant a task transitions.

## Event Types

| SSE Event | Trigger | Fields |
|---|---|---|
| `thinking` | `LLM_CHAT_COMPLETE` task scheduled | `content` (task ref name) |
| `tool_call` | Worker (SIMPLE) task completed | `toolName`, `args` |
| `tool_result` | Worker (SIMPLE) task completed | `toolName`, `result` |
| `guardrail_pass` | Guardrail task completed with `passed: true` | `guardrailName` |
| `guardrail_fail` | Guardrail task completed with `passed: false` | `guardrailName`, `content` (message) |
| `handoff` | `SUB_WORKFLOW` task scheduled | `target` (agent name) |
| `waiting` | `HUMAN` task enters `IN_PROGRESS` | `pendingTool` (tool name, parameters) |
| `error` | Task failed or workflow terminated | `content` (reason), `toolName` (task ref) |
| `done` | Workflow completed | `output` (final result) |

Every event includes: `id` (monotonic sequence), `type`, `workflowId`, `timestamp`.

## SSE Wire Format

```
id:1
event:thinking
data:{"id":1,"type":"thinking","workflowId":"abc-123","content":"my_agent_llm","timestamp":1709721234000}

id:2
event:tool_call
data:{"id":2,"type":"tool_call","workflowId":"abc-123","toolName":"get_weather","args":{"city":"NYC"},"timestamp":1709721234567}

id:3
event:tool_result
data:{"id":3,"type":"tool_result","workflowId":"abc-123","toolName":"get_weather","result":"72F sunny","timestamp":1709721235123}

id:4
event:done
data:{"id":4,"type":"done","workflowId":"abc-123","output":{"result":"The weather in NYC is 72F and sunny.","finishReason":"STOP"},"timestamp":1709721236000}
```

Heartbeats are sent as SSE comments (`: heartbeat\n\n`) every 15 seconds to prevent proxy idle timeouts.

## Server-Side Components

### AgentSSEEvent (model)

Event DTO with factory methods for each event type. Uses `@JsonInclude(NON_NULL)` for clean serialization — only populated fields appear in the JSON payload.

**File:** `runtime/.../model/AgentSSEEvent.java`

### AgentStreamRegistry (service)

Manages the lifecycle of SSE connections and event buffers.

**File:** `runtime/.../service/AgentStreamRegistry.java`

**Data structures:**
- `ConcurrentHashMap<workflowId, CopyOnWriteArrayList<SseEmitter>>` — connected clients per workflow. Multiple clients can watch the same workflow.
- `ConcurrentHashMap<workflowId, BoundedEventBuffer>` — ring buffer (200 events) per workflow for reconnection replay.
- `ConcurrentHashMap<childWfId, parentWfId>` — aliases for sub-workflow event forwarding in multi-agent workflows.
- `ConcurrentHashMap<workflowId, AtomicLong>` — monotonic event ID sequence per workflow.

**Key operations:**
- `register(workflowId, lastEventId)` — creates `SseEmitter(0L)` (no timeout), replays missed events if `lastEventId` is provided.
- `send(workflowId, event)` — resolves aliases, assigns sequence ID, buffers event, broadcasts to all connected emitters.
- `complete(workflowId)` — completes all emitters, schedules buffer cleanup after 5 minutes.
- `registerAlias(childWfId, parentWfId)` — forwards child workflow events to parent's stream.

**Scheduled tasks:**
- Heartbeat: every 15 seconds, sends `: heartbeat` comment to all open connections.
- Cleanup: every 60 seconds, removes event buffers for workflows that completed >5 minutes ago.

### AgentEventListener (service)

Translates Conductor's internal task/workflow callbacks into SSE events.

**File:** `runtime/.../service/AgentEventListener.java`

Implements both `TaskStatusListener` and `WorkflowStatusListener`. Annotated `@Component @Primary` to override Conductor's default stub listeners.

**Conductor callback → SSE event mapping:**

| Callback | Condition | SSE Event |
|---|---|---|
| `onTaskScheduled` | type = `LLM_CHAT_COMPLETE` | `thinking` |
| `onTaskScheduled` | type = `SUB_WORKFLOW` | `handoff` + register alias |
| `onTaskInProgress` | type = `HUMAN` | `waiting` |
| `onTaskCompleted` | `isToolTask()` = true | `tool_call` + `tool_result` |
| `onTaskCompleted` | ref contains "guardrail" | `guardrail_pass` or `guardrail_fail` |
| `onTaskFailed` | any | `error` |
| `onTaskTimedOut` | any | `error` |
| `onWorkflowCompletedIfEnabled` | — | `done` |
| `onWorkflowTerminatedIfEnabled` | — | `error` |
| `onWorkflowPausedIfEnabled` | — | `waiting` |

**Tool task detection (`isToolTask`):** Returns `true` for `SIMPLE` tasks, excluding all known system task types (`LLM_CHAT_COMPLETE`, `SWITCH`, `DO_WHILE`, `INLINE`, `SET_VARIABLE`, `FORK_JOIN_DYNAMIC`, `JOIN`, `SUB_WORKFLOW`, `HUMAN`, `TERMINATE`, `HTTP`, `CALL_MCP_TOOL`).

**Important Conductor listener detail:** `WorkflowExecutorOps.notifyWorkflowStatusListener()` calls the `*IfEnabled` variants (`onWorkflowCompletedIfEnabled`, `onWorkflowTerminatedIfEnabled`, etc.), not the plain `onWorkflowCompleted`/`onWorkflowTerminated`. The default interface methods check `WorkflowDef.workflowStatusListenerEnabled`. Our implementation overrides both paths and delegates to shared private methods.

### AgentController (endpoints)

**File:** `runtime/.../controller/AgentController.java`

Three new endpoints added to the existing `/api/agent` controller:

```
GET  /api/agent/stream/{workflowId}      SSE event stream
POST /api/agent/{workflowId}/respond      HITL response
GET  /api/agent/{workflowId}/status       Polling fallback
```

**Stream endpoint:** Returns `SseEmitter`. Supports `Last-Event-ID` header for reconnection. No `produces` annotation — `SseEmitter` handles content-type negotiation internally (adding `produces = "text/event-stream"` causes `HttpMediaTypeNotAcceptableException` with Conductor's `ApplicationExceptionMapper`).

**Respond endpoint:** Finds the pending `HUMAN` task in the workflow, constructs a `TaskResult`, and calls `executionService.updateTask()`. Accepts JSON body with arbitrary output fields (e.g., `{"approved": true}`, `{"approved": false, "reason": "..."}`, `{"message": "..."}`).

**Status endpoint:** Lightweight polling fallback. Returns workflow status, output (if complete), and pending tool info (if waiting for HITL).

### AgentService (service)

**File:** `runtime/.../service/AgentService.java`

Three new methods:
- `openStream(workflowId, lastEventId)` — delegates to `AgentStreamRegistry.register()`.
- `respond(workflowId, output)` — finds pending HUMAN task via `executionService.getExecutionStatus()`, creates `TaskResult`, calls `executionService.updateTask()`.
- `getStatus(workflowId)` — returns `{workflowId, status, isComplete, isRunning, isWaiting, output, pendingTool}`.

### Configuration

```properties
# application.properties
conductor.task-status-listener.type=agent
conductor.workflow-status-listener.type=agent
```

Setting these to `agent` disables Conductor's default stub listeners (which have `@ConditionalOnProperty(havingValue = "stub", matchIfMissing = true)`) and allows Spring to inject our `@Primary` `AgentEventListener` bean.

`@EnableScheduling` on the main `AgentRuntime` class enables the heartbeat and cleanup `@Scheduled` tasks.

## Client-Side Components

### Python SSE Client

**File:** `python/src/agentspan/agents/runtime/runtime.py`

Three new methods on `AgentRuntime`:

**`_stream_sse(workflow_id)`** — Core SSE consumer. Opens a streaming HTTP GET to `/api/agent/stream/{workflowId}` using the `requests` library. Auto-reconnects with `Last-Event-ID` header on connection drops. Yields `AgentEvent` objects. Terminates on `done` or `error` events.

```python
# Connection setup
url = f"{server_url}/agent/stream/{workflow_id}"
headers = {"Accept": "text/event-stream"}
requests.get(url, headers=headers, stream=True, timeout=(5, None))
```

- Connect timeout: 5 seconds
- Read timeout: None (indefinite — controlled by server lifecycle + heartbeats)
- On first connect failure: raises `_SSEUnavailableError` (triggers polling fallback)
- On subsequent connection loss: waits 1 second, reconnects with `Last-Event-ID`

**`_parse_sse(lines)`** — Static method. Parses the SSE wire format from an iterator of lines. Handles `event:`, `id:`, `data:` fields and `:comment` lines (heartbeats). Yields dicts of `{event, id, data}`.

**`_sse_to_agent_event(sse_event, workflow_id)`** — Static method. Converts a parsed SSE event dict into an `AgentEvent` dataclass, mapping camelCase JSON fields to Python attributes.

### Graceful Fallback

The `stream()` method tries SSE first and falls back to the existing polling implementation:

```python
if self._config.streaming_enabled:
    try:
        yield from self._stream_sse(handle.workflow_id)
        return
    except _SSEUnavailableError:
        logger.info("SSE unavailable, falling back to polling")

# Existing polling-based stream
yield from self._poll_stream(handle)
```

### Configuration

**File:** `python/src/agentspan/agents/runtime/config.py`

```python
streaming_enabled: bool = True  # default
# Env var: AGENTSPAN_STREAMING_ENABLED
```

### AgentHandle.stream()

**File:** `python/src/agentspan/agents/result.py`

```python
class AgentHandle:
    def stream(self) -> Iterator[AgentEvent]:
        return self._runtime._stream_sse(self.workflow_id)
```

## Reconnection Protocol

SSE has built-in reconnection support via the `Last-Event-ID` mechanism:

1. Server assigns monotonic sequence IDs to each event.
2. Client tracks the last received event ID.
3. On connection drop, client reconnects with `Last-Event-ID: N` header.
4. Server replays all buffered events with ID > N before resuming live events.

The server retains event buffers for 5 minutes after workflow completion, allowing late reconnections.

```
Client                         Server
  │                               │
  │─── GET /stream/abc-123 ──────→│  (initial connect)
  │←── SSE: id=1 thinking ───────│
  │←── SSE: id=2 tool_call ──────│
  │                               │
  ╳ connection drops               │
  │                               │←── id=3 tool_result (buffered)
  │                               │←── id=4 done (buffered)
  │                               │
  │─── GET /stream/abc-123 ──────→│  Last-Event-ID: 2
  │←── SSE: id=3 tool_result ────│  (replay)
  │←── SSE: id=4 done ───────────│  (replay)
  │←── stream ends ──────────────│
```

## Sub-Workflow Event Forwarding

Multi-agent workflows use sub-workflows for agent handoffs. Events from child workflows are forwarded to the parent's SSE stream via aliases:

1. When a `SUB_WORKFLOW` task is scheduled, `AgentEventListener` calls `streamRegistry.registerAlias(childWfId, parentWfId)`.
2. When events are emitted for the child workflow ID, `AgentStreamRegistry.send()` resolves the alias and routes to the parent's emitters and buffer.
3. Aliases are cleaned up when the parent workflow completes.

This means a client connected to the parent workflow's stream receives events from all child agent executions transparently.

## HITL (Human-in-the-Loop) Flow

```
Client                         Server
  │                               │
  │─── GET /stream/wf-123 ───────→│
  │←── SSE: thinking ────────────│
  │←── SSE: tool_call ───────────│  (tool requires approval)
  │←── SSE: waiting ─────────────│  pendingTool: {tool_name, parameters}
  │                               │
  │  (user reviews tool call)      │
  │                               │
  │─── POST /wf-123/respond ─────→│  {"approved": true}
  │                               │  → updateTask(HUMAN task)
  │←── SSE: tool_result ─────────│
  │←── SSE: done ────────────────│
```

The `waiting` event includes `pendingTool` with the tool name and parameters, so the client can display what the agent wants to do for human review.

## File Inventory

### Server (Java)

| File | Purpose |
|---|---|
| `runtime/.../model/AgentSSEEvent.java` | Event DTO with factory methods |
| `runtime/.../service/AgentStreamRegistry.java` | SSE emitter + buffer management |
| `runtime/.../service/AgentEventListener.java` | Conductor callback → SSE translation |
| `runtime/.../service/AgentService.java` | `openStream()`, `respond()`, `getStatus()` |
| `runtime/.../controller/AgentController.java` | 3 new REST endpoints |
| `runtime/src/main/resources/application.properties` | Listener type = `agent` |

### Client (Python)

| File | Purpose |
|---|---|
| `python/.../runtime/runtime.py` | `_stream_sse()`, `_parse_sse()`, `_sse_to_agent_event()` |
| `python/.../runtime/config.py` | `streaming_enabled` field + env var |
| `python/.../result.py` | `AgentHandle.stream()` |

## Future Work

- **LLM token streaming**: Requires intercepting the Conductor AI module's chat completion call to stream tokens as they arrive (currently the `LLM_CHAT_COMPLETE` task completes atomically).
- **Multi-instance event bus**: For horizontal scaling, replace in-memory buffers with Redis Streams or Kafka so any server instance can serve any workflow's SSE stream.
- **Typed HITL responses**: Schema-validated response types beyond the current free-form JSON.
