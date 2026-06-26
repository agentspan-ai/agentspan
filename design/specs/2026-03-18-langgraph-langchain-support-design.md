# LangGraph & LangChain Support for Agentspan

**Date:** 2026-03-18
**Status:** Approved

## Summary

Add support for running LangGraph `CompiledStateGraph` and LangChain `AgentExecutor` objects on Agentspan. Both frameworks manage their own LLM calls and state internally, so they are treated as **black-box workers** — a single Conductor SIMPLE task wraps the entire graph/executor execution, with intermediate node events streamed back to Agentspan's SSE infrastructure via non-blocking HTTP push.

## Scope

- Python SDK only (TypeScript SDK is a follow-up)
- LangGraph `CompiledStateGraph` (including `create_react_agent` output)
- LangChain `AgentExecutor`
- Auto-detect input/output format
- Map `session_id` to LangGraph `thread_id` for checkpointer-enabled graphs
- Stream intermediate LangGraph node events to Agentspan SSE via HTTP push

## Architecture

### Execution Model

LangGraph and LangChain manage their own LLM calls, tool routing, and state internally. Agentspan wraps the entire graph/executor as a single Conductor SIMPLE task — a "passthrough execution":

```
User prompt
    │
    ▼
Agentspan Server ──compiles──▶ Passthrough WorkflowDef
    │                          (one SIMPLE task, no LLM_CHAT_COMPLETE task)
    ▼
Conductor dispatches SIMPLE task
    │
    ▼
Python Worker (SDK side)
    ├── graph.stream() ──events (non-blocking)──▶ POST /agent/events/{executionId}
    │                                                  │
    │                                                  ▼
    │                                          AgentStreamRegistry.send()
    │                                                  │
    │                                                  ▼
    │                                          SSE clients (UI, SDK polling)
    └── returns final output ──▶ task COMPLETED ──▶ AgentEventListener fires `done` event
```

This is different from the existing OpenAI/ADK framework support, where tools are individually extracted and registered as separate Conductor workers and the LLM is called via Conductor's `LLM_CHAT_COMPLETE` task type.

### `done` Event Responsibility

The `done` SSE event is fired by the **existing `AgentEventListener`** when the Conductor execution transitions to COMPLETED, exactly as it does for native agents. The Python LangGraph/LangChain worker does NOT push a `done` event. The worker only pushes intermediate events: `thinking`, `tool_call`, and `tool_result`.

### Contrast with OpenAI/ADK Support

| Concern | OpenAI/ADK | LangGraph/LangChain |
|---------|-----------|---------------------|
| LLM call | Conductor `LLM_CHAT_COMPLETE` task | Managed internally by framework |
| Tool calls | Each tool = separate Conductor SIMPLE task | Tools run inside framework, invisible to Conductor |
| Compilation | Full `AgentConfig` → LLM+tool loop execution | Passthrough execution: one SIMPLE task |
| Worker count | One per tool | One per graph/executor |
| Visibility | Per-task granularity | Node-level events via HTTP push |

## Components

### 1. Python SDK — Worker Architecture

The LangGraph/LangChain worker is **pre-wrapped**: `make_langgraph_worker` returns a `tool_worker(task: Task) -> TaskResult` function directly, with a closure over the graph object. It does **not** go through `make_tool_worker`. This avoids double-wrapping (which would break the `Task` input parsing) and gives direct access to `task.workflow_instance_id`.

The worker function signature is:
```python
def tool_worker(task: Task) -> TaskResult:
    execution_id = task.workflow_instance_id  # Conductor's workflowInstanceId maps to our executionId
    prompt = task.input_data.get("prompt", "")
    session_id = task.input_data.get("session_id", "") or ""
    # ... run graph.stream(), push events, return result
```

The `WorkerInfo.func` field stores this pre-wrapped `tool_worker` function.

**Registration path**: `_start_framework()` and `_start_framework_async()` in `runtime.py` check the `framework` identifier before dispatching to the worker registration helper. For `"langgraph"` and `"langchain"` frameworks, they call a new `_register_passthrough_worker(worker)` method instead of `_register_framework_workers(workers)`. `_register_passthrough_worker` registers the pre-wrapped `tool_worker` directly via `@worker_task` without calling `make_tool_worker`. The existing `_register_framework_workers` (which calls `make_tool_worker`) is NOT called for these frameworks.

`_register_passthrough_worker` uses a dedicated `_passthrough_task_def(name)` helper (mirroring `_default_task_def`) that sets `timeout_seconds = 600` and `response_timeout_seconds = 600`, overriding the default 120 s to accommodate long-running graphs.

### 2. Python SDK — `frameworks/langgraph.py` (new)

Provides:
- `serialize_langgraph(graph)` — creates a single `WorkerInfo` containing a pre-wrapped `tool_worker` closure over the graph
- `make_langgraph_worker(graph, name, server_url, auth_key, auth_secret)` — builds the `tool_worker(task)` function

The worker function:
1. Extracts `prompt`, `session_id` from `task.input_data`; gets `execution_id = task.workflow_instance_id`
2. Auto-detects input format from `graph.get_input_jsonschema()`
3. Calls `graph.stream(input, config, stream_mode="updates")` in a loop
4. For each chunk, fires a **non-blocking** HTTP POST (using a background thread) to `POST /agent/events/{executionId}`
5. Accumulates the final state from the last chunk
6. Extracts the output from the accumulated state
7. Returns `TaskResult(status=COMPLETED, output_data={"result": output})`

On error (including checkpointer-related exceptions from LangGraph), returns `TaskResult(status=FAILED, reason_for_incompletion=str(e))` so Conductor can retry per the task definition's retry policy.

**Non-blocking push implementation**: Each event POST is dispatched to a `ThreadPoolExecutor(max_workers=4)` that is shared for the lifetime of the worker process. The worker does not wait for the POST to complete before processing the next graph node. If the server is unreachable, the thread pool silently drops the failed POSTs (errors are logged at DEBUG level only).

**Task timeout**: The passthrough workflow uses a `task_timeout_seconds = 600` (10 minutes) instead of the default 120 s, to accommodate long-running graphs. This is set in the `WorkerInfo` metadata and applied at worker registration time.

### 3. Python SDK — `frameworks/langchain.py` (new)

Provides:
- `serialize_langchain(executor)` — creates a single `WorkerInfo` containing a pre-wrapped `tool_worker` closure over the executor
- `make_langchain_worker(executor, name, server_url, auth_key, auth_secret)` — builds the `tool_worker(task)` function

LangChain streaming uses a custom `BaseCallbackHandler` injected into `executor.invoke(callbacks=[handler])`. The handler fires non-blocking HTTP POSTs on `on_tool_start`, `on_tool_end`, and `on_llm_start`.

`session_id` is not passed to `AgentExecutor` (it has no checkpointing support).

### 4. Python SDK — `frameworks/serializer.py` (modified)

Framework detection uses both module prefix AND type-name checking to avoid false positives:

```python
def detect_framework(agent_obj: Any) -> Optional[str]:
    from agentspan.agents.agent import Agent
    if isinstance(agent_obj, Agent):
        return None

    # Precise type-name check for LangGraph CompiledStateGraph
    type_name = type(agent_obj).__name__
    if type_name in ("CompiledStateGraph", "Pregel", "CompiledGraph"):
        return "langgraph"

    # LangChain AgentExecutor
    if type_name == "AgentExecutor":
        return "langchain"

    # Existing module-prefix fallback for openai and google_adk
    module = type(agent_obj).__module__ or ""
    for prefix, framework_id in _FRAMEWORK_DETECTION.items():
        if module == prefix or module.startswith(prefix + "."):
            return framework_id
    return None
```

Update `serialize_agent()` to dispatch to custom serializers for LangGraph and LangChain:

```python
def serialize_agent(agent_obj: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    framework = detect_framework(agent_obj)
    if framework == "langgraph":
        from agentspan.agents.frameworks.langgraph import serialize_langgraph
        return serialize_langgraph(agent_obj)
    if framework == "langchain":
        from agentspan.agents.frameworks.langchain import serialize_langchain
        return serialize_langchain(agent_obj)
    # ... existing generic deep-serialization logic
```

The `_FRAMEWORK_DETECTION` prefix map retains `"agents"` and `"google.adk"` for the generic path but does not add `"langgraph"` or `"langchain"` since those use the type-name check above.

### 5. Java Server — `LangGraphNormalizer.java` (new)

Normalizes LangGraph rawConfig → passthrough `AgentConfig`.

rawConfig sent by SDK:
```json
{ "name": "my_graph", "_worker_name": "my_graph" }
```

`name` = Conductor workflow name (derived from the Python graph's `.name` attribute, sanitized for valid Conductor names). `_worker_name` = Conductor task definition name for the SIMPLE task. When the graph has no explicit name, both default to `"langgraph_agent"`.

Produces:
```java
AgentConfig {
  name: "my_graph",
  metadata: { "_framework_passthrough": true },
  tools: [ ToolConfig { name: "my_graph", toolType: "worker" } ]
  // model is intentionally null — passthrough path does not use model
}
```

### 6. Java Server — `LangChainNormalizer.java` (new)

Same structure as `LangGraphNormalizer`. `frameworkId()` returns `"langchain"`.

### 7. Java Server — `AgentCompiler.java` (modified)

The passthrough guard is the **very first check** in `compile()`, before `isExternal()` and before any model-dependent branching:

```java
public WorkflowDef compile(AgentConfig config) {
    // Passthrough check MUST come first — passthrough AgentConfigs have no model.
    // Checking isExternal() or branching on tools before this would crash on null model.
    if (isFrameworkPassthrough(config)) {
        return compileFrameworkPassthrough(config);
    }

    if (config.isExternal()) {
        throw new IllegalArgumentException(...);
    }
    // ... existing logic unchanged
}

private boolean isFrameworkPassthrough(AgentConfig config) {
    return config.getMetadata() != null
        && Boolean.TRUE.equals(config.getMetadata().get("_framework_passthrough"));
}
```

`compileFrameworkPassthrough` creates a minimal `WorkflowDef`:

```
WorkflowDef:
  name: {config.getName()}
  version: 1
  inputParameters: [prompt, session_id, media]
  tasks:
    - type: SIMPLE
      name: {tools[0].name}            # = Conductor task definition name (the worker)
      taskReferenceName: _fw_task      # _fw_ prefix suppresses AgentEventListener tool events
      inputParameters:
        prompt:     ${workflow.input.prompt}
        session_id: ${workflow.input.session_id}
        media:      ${workflow.input.media}
  outputParameters:
    result: ${_fw_task.output.result}
  metadata:
    agent_sdk: "langgraph" | "langchain"  (stamped by AgentService.start())
```

The `_fw_` prefix on the `taskReferenceName` is a naming convention recognized by `AgentEventListener.isToolTask()`. A one-line check is added to `isToolTask()`:

```java
// Skip framework passthrough wrapper tasks — they emit their own fine-grained events
if (task.getReferenceTaskName() != null && task.getReferenceTaskName().startsWith("_fw_")) {
    return false;
}
```

This prevents the listener from emitting a spurious `tool_call`/`tool_result` pair for the entire passthrough worker task completion, which would duplicate the fine-grained events already pushed by the Python worker.

### 8. Java Server — Event Push Endpoint (new)

New endpoint in `AgentController` (controller is mapped to `/api/agent`):

```
POST /api/agent/events/{executionId}
Headers: X-Auth-Key, X-Auth-Secret (same auth as all other /api/agent/* endpoints)
Body: { "type": "thinking|tool_call|tool_result", "content": "...", "toolName": "...", "args": {...}, "result": "..." }
Response: 200 OK always (even if executionId has no listeners — events are silently dropped
         by AgentStreamRegistry when no emitters are registered, which is correct behavior
         for the case where no client has connected to the SSE stream yet)
```

The Python worker constructs the URL as `{server_url}/api/agent/events/{execution_id}` using the same `server_url` already available to the worker process (via `AgentConfig` env vars or the SDK runtime config).

`AgentService.pushFrameworkEvent(executionId, eventMap)` translates the map to the appropriate `AgentSSEEvent` factory and calls `streamRegistry.send(executionId, event)`.

Auth note: same `X-Auth-Key`/`X-Auth-Secret` header validation applied to all `/agent/*` endpoints is applied here. In the current implementation, auth validation is permissive (warn-only) when no keys are configured, consistent with the rest of the API.

## Input/Output Auto-Detection

### Input Format (LangGraph)

At worker invocation time, call `graph.get_input_jsonschema()`:

- If schema has a `messages` property → wrap prompt as `HumanMessage`:
  `{"messages": [HumanMessage(content=prompt)]}`
- Otherwise → find the first `string`-typed required property in the schema and use it:
  `{first_required_string_key: prompt}`, falling back to `{"prompt": prompt}`

### Output Extraction (LangGraph)

`graph.stream(stream_mode="updates")` emits per-node deltas (not full state). To obtain the final accumulated state, the worker calls `graph.stream(stream_mode="updates")` for event emission and **also tracks the full final state by accumulating updates**, or more simply: after `graph.stream()` completes, calls `graph.get_state(config).values` if a checkpointer is configured, or re-invokes `graph.invoke()` (which is idempotent since we already have the streamed final result available from the last "values" chunk).

**Practical implementation**: Use `stream_mode=["updates", "values"]` (LangGraph supports a list of modes). The `"values"` stream emits the full state after each superstep; the `"updates"` stream emits per-node deltas for event mapping. The worker uses the last `"values"` chunk as the final state for output extraction, and each `"updates"` chunk for SSE event emission.

Final state extraction:
- If state has `messages` key → iterate in reverse, return first `AIMessage.content` found
- Otherwise → JSON-serialize the state dict as output string

### LangChain AgentExecutor

- Input: `{"input": prompt}` (standard `AgentExecutor` interface)
- Output: `result["output"]` (standard `AgentExecutor` result)

## Session Persistence

If `session_id` is non-empty, pass it as `{"configurable": {"thread_id": session_id}}` in the LangGraph `RunnableConfig`. The user is responsible for providing a checkpointer when compiling their graph.

If LangGraph raises a `ValueError` or `RuntimeError` due to checkpointer configuration (e.g., `interrupt()` nodes without a checkpointer), the worker catches it and returns `TaskResult(status=FAILED, reason_for_incompletion=str(e))`. Conductor will retry per the task definition's retry policy (2 retries, linear backoff, 2 s delay). This gives observability without swallowing errors.

LangChain `AgentExecutor` has no checkpointing; `session_id` is unused on that path.

## SSE Event Mapping (LangGraph)

`graph.stream(stream_mode="updates")` emits `{node_name: {state_updates}}` per node execution.

| LangGraph stream chunk | Agentspan SSE event |
|------------------------|---------------------|
| Any node starts (node_name key appears) | `thinking(executionId, node_name)` |
| `messages` contains `AIMessage` with `tool_calls` | `tool_call(executionId, tool_name, args)` per call |
| `messages` contains `ToolMessage` | `tool_result(executionId, tool_name, content)` |
| Final `AIMessage` with content and no tool_calls | `thinking(executionId, "agent")` with content |

The `done` event is **not** emitted by the Python worker. It is emitted by the existing `AgentEventListener` when the Conductor workflow reaches COMPLETED status.

## SSE Event Mapping (LangChain)

LangChain callback handlers fire synchronously during `AgentExecutor.invoke()`. The custom callback handler dispatches each event non-blocking to the shared thread pool.

| LangChain callback | Agentspan SSE event |
|--------------------|---------------------|
| `on_tool_start(tool, input)` | `tool_call(executionId, tool, input)` |
| `on_tool_end(output)` | `tool_result(executionId, tool, output)` |
| `on_llm_start` | `thinking(executionId, "llm")` |

## Test-First Implementation Strategy

Implementation proceeds example by example, test written first:

1. **LangGraph ReAct agent** — `create_react_agent` with tools; test basic invocation + output extraction
2. **LangGraph custom StateGraph** — custom nodes, non-messages state schema; test auto-detect input/output
3. **LangGraph with checkpointer** — session_id → thread_id, conversation continuity across calls
4. **LangChain AgentExecutor** — legacy executor with tools

For each example:
- Python SDK test: creates graph/executor, calls `runtime.run()`, asserts on output
- SSE event test: verifies intermediate `thinking`/`tool_call`/`tool_result` events are pushed
- Server-side unit test: `POST /agent/events/{executionId}` endpoint → `AgentStreamRegistry.send()` → SSE client receives event

## File Changes

### Python SDK (`sdk/python/src/agentspan/agents/`)

| File | Change |
|------|--------|
| `frameworks/langgraph.py` | New — LangGraph serializer + pre-wrapped worker factory |
| `frameworks/langchain.py` | New — LangChain serializer + pre-wrapped worker factory |
| `frameworks/__init__.py` | Export new symbols |
| `frameworks/serializer.py` | Update `detect_framework()` with type-name checks; update `serialize_agent()` to dispatch to custom serializers |
| `runtime/runtime.py` | Add `_register_passthrough_worker()` + `_passthrough_task_def()`; update `_start_framework()` + `_start_framework_async()` to branch on framework ID |

### Java Server (`server/src/main/java/dev/agentspan/runtime/`)

| File | Change |
|------|--------|
| `normalizer/LangGraphNormalizer.java` | New — rawConfig → passthrough AgentConfig |
| `normalizer/LangChainNormalizer.java` | New — same for LangChain |
| `compiler/AgentCompiler.java` | Add passthrough guard as first check in `compile()`; add `compileFrameworkPassthrough()` |
| `controller/AgentController.java` | Add `POST /api/agent/events/{executionId}` |
| `service/AgentService.java` | Add `pushFrameworkEvent()` |
| `service/AgentEventListener.java` | Add `_fw_` prefix check to `isToolTask()` |

## Out of Scope

- TypeScript SDK support (follow-up)
- LangGraph Platform (`RemoteGraph`) support
- LangGraph `interrupt()` / HITL within a graph
- LangGraph subgraph topology visibility in the Agentspan UI
- LangChain LCEL chains (not `AgentExecutor`)
