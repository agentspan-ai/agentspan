# Claude Agent SDK Integration Design

**Date:** 2026-03-27
**Status:** Draft
**Framework:** `claude_agent_sdk` (Python, passthrough mode)

## Overview

Add Claude Agent SDK as a supported framework in agentspan. Users pass `ClaudeAgentOptions` to `runtime.run()` or `runtime.start()`, and agentspan runs it as a durable Conductor SUB_WORKFLOW with passthrough execution. Agentspan hooks into the Claude Agent SDK's hook system for real-time streaming events and persisted task metadata.

## Goals

1. **Use Case A**: Users with existing Claude Agent SDK agents bring them into agentspan for durability, orchestration, and observability.
2. **Use Case C**: Claude Agent SDK agents can be invoked as worker tools within larger agentspan workflows (Phase 1 via `@tool` wrapper, Phase 2 via `runtime.register()` + named handoffs).

## Non-Goals

- Full extraction (decomposing Claude Agent SDK agents into individual Conductor tool tasks). The Claude Agent SDK is a full runtime with built-in tools (Read, Edit, Bash, etc.), hooks, sessions, and permissions. Extracting these would lose most of its value.
- TypeScript support (Python first, TypeScript follow-up).

## Architecture

### Execution Model: Passthrough with Hooks

```
User code                          Agentspan                          Conductor
─────────                          ─────────                          ─────────
runtime.run(options, prompt)
    │
    ├─ detect_framework() → "claude_agent_sdk"
    ├─ serialize_claude_agent_sdk(options) → (raw_config, [WorkerInfo])
    │   raw_config: {name, _worker_name}
    │   WorkerInfo: func=None (filled later)
    │
    ├─ _build_passthrough_func() → make_claude_agent_sdk_worker()
    │   Closure captures: options, server_url, auth credentials
    │
    ├─ _register_passthrough_worker() → Conductor task def (600s timeout)
    │
    ├─ POST /api/agent/start {framework: "claude_agent_sdk", rawConfig}
    │                                  │
    │                                  ├─ NormalizerRegistry → ClaudeAgentSdkNormalizer
    │                                  │   Returns AgentConfig with _framework_passthrough=true
    │                                  │
    │                                  ├─ AgentCompiler.compileFrameworkPassthrough()
    │                                  │   Produces: WorkflowDef with single SIMPLE task
    │                                  │
    │                                  └─ Start execution ─────────────────► Conductor
    │                                                                          │
    │                                                                    Worker polls task
    │                                                                          │
    │   ┌──────────────────────────────────────────────────────────────────────┘
    │   │
    │   ▼ tool_worker(task) runs:
    │   1. Inject execution credentials → os.environ
    │   2. Create metadata dict
    │   3. Build agentspan hooks (close over metadata + execution_id)
    │   4. Merge user hooks + agentspan hooks (user first)
    │   5. asyncio.run(_run_query(prompt, merged_options))
    │      └─ async for message in query(prompt, options):
    │         ├─ Hooks fire: PreToolUse, PostToolUse, SubagentStart, etc.
    │         │   ├─ Push stream events via HTTP POST /api/agent/events/{executionId}
    │         │   └─ Mutate metadata dict (tool counts, tools_used, etc.)
    │         └─ Collect ResultMessage → result text + token usage
    │   6. Return TaskResult with {result, ...metadata}
    │
    └─ Poll/stream until complete → AgentResult
```

## Components

### 1. Python SDK: Framework Detection

**File:** `sdk/python/src/agentspan/agents/frameworks/serializer.py`

Add to `detect_framework()`:
- Type-name check: `if type_name == "ClaudeAgentOptions": return "claude_agent_sdk"` (before the module prefix fallback, matching the LangGraph/LangChain type-name pattern)
- No `_FRAMEWORK_DETECTION` entry needed — type-name check is sufficient (LangGraph and LangChain also rely on type-name checks, not the prefix dict)

Add to `serialize_agent()`:
- Short-circuit branch: `if framework == "claude_agent_sdk": from ...claude_agent_sdk import serialize_claude_agent_sdk; return serialize_claude_agent_sdk(agent_obj)`

### 2. Python SDK: Serializer

**New file:** `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py`

```python
def serialize_claude_agent_sdk(options: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
```

- Extracts a name from options (sanitized system_prompt prefix, or default `"claude_agent_sdk_agent"`)
- Returns `raw_config = {"name": name, "_worker_name": name}`
- Returns single WorkerInfo with all required fields (matching the LangChain pattern):
  ```python
  WorkerInfo(
      name=name,
      description=f"Claude Agent SDK passthrough worker for {name}",
      input_schema={
          "type": "object",
          "properties": {
              "prompt": {"type": "string"},
              "session_id": {"type": "string"},
          },
      },
      func=None,  # Filled by _build_passthrough_func() with pre-wrapped Task→TaskResult closure
  )
  ```
- The `ClaudeAgentOptions` object itself is NOT serialized to JSON — it stays in the worker closure

### 3. Python SDK: Passthrough Worker

**Same file:** `claude_agent_sdk.py`

```python
def make_claude_agent_sdk_worker(
    options: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Callable:
```

Returns a pre-wrapped `tool_worker(task: Task) -> TaskResult` closure (already in `Task → TaskResult` form, bypasses `make_tool_worker` via `_register_passthrough_worker`) that:

1. **Extracts cwd**: Gets `cwd` from `task.input_data.get("cwd")`. If present, sets it on the merged options so the Claude Agent SDK executes file operations in the correct directory.
2. **Injects credentials**: Same pattern as LangChain worker — resolves execution-level credentials from `_workflow_credentials` registry via execution token, injects into `os.environ`, cleans up in `finally`.
3. **Creates metadata dict**: `{tool_call_count, tool_error_count, subagent_count, tools_used (set)}` — shared with hooks via closure.
4. **Builds agentspan hooks**: `_build_agentspan_hooks(execution_id, server_url, auth_key, auth_secret, metadata)` — returns a dict of hook event → list of HookMatcher.
5. **Merges hooks**: User hooks run first, agentspan hooks appended after. Uses duck-typed copy of options (handles dict, Pydantic, dataclass, or plain object).
6. **Runs query**: `asyncio.run(_run_query(prompt, merged_options))` — drives the async generator in a new event loop.
7. **Returns TaskResult on success**: `output_data = {"result": result_text, "tools_used": sorted(metadata["tools_used"]), ...metadata, "token_usage": ...}`
8. **Returns TaskResult on failure**: `except Exception` returns `TaskResult(status=TaskResultStatus.FAILED, reason_for_incompletion=str(exc))`, matching the LangChain error handling pattern.

**`_run_query(prompt, options)`** — async coroutine:
- Iterates `async for message in query(prompt=prompt, options=options)`
- Collects text from `AssistantMessage` blocks as fallback
- Captures `result` and `usage` from `ResultMessage`
- Returns `(result_output, token_usage)`

### 4. Python SDK: Agentspan Hooks

Built by `_build_agentspan_hooks()`, all hooks are defensive (try/except wrapping — instrumentation must never crash the agent).

| Hook Event | Action | Stream Event | Metadata Mutation |
|---|---|---|---|
| `PreToolUse` | Report tool call start | `{"type": "tool_call", "toolName": ..., "toolUseId": ...}` | `tool_call_count += 1`, `tools_used.add(name)` |
| `PostToolUse` | Report tool call end | `{"type": "tool_result", "toolName": ..., "toolUseId": ...}` | (none beyond PreToolUse) |
| `PostToolUseFailure` | Report tool error | `{"type": "tool_error", "toolName": ..., "error": ...}` | `tool_error_count += 1` |
| `SubagentStart` | Report subagent spawn | `{"type": "subagent_start", "agent_id": ...}` | `subagent_count += 1` |
| `SubagentStop` | Report subagent done | `{"type": "subagent_stop", "agent_id": ...}` | (none) |
| `Notification` | Forward status | `{"type": "notification", "message": ...}` | (none) |
| `Stop` | Finalize | `{"type": "agent_stop"}` | (none — metadata already populated by other hooks) |

**Hook callback signature:** The exact hook API must be verified against the installed `claude-agent-sdk` version during implementation. The Claude Agent SDK may use a class-based hook system or a callback-based system — the implementer should:
1. Install `claude-agent-sdk` and inspect `ClaudeAgentOptions.hooks` type
2. Check the actual callback signature (likely `async def hook(input_data, tool_use_id, context) -> dict` based on docs, but must be confirmed)
3. Adapt `_build_agentspan_hooks()` to match the actual API

All agentspan hooks return `{}` (no interference with agent execution).

**Import paths** (verify against actual package):
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage
# or possibly:
from claude_code_sdk import query, ClaudeCodeOptions, AssistantMessage, ResultMessage
```
The exact package name and import paths must be confirmed at implementation time. The SDK is published as `claude-agent-sdk` on PyPI.

Event delivery uses `_push_event_nonblocking()` — fire-and-forget HTTP POST via module-level `ThreadPoolExecutor(max_workers=4)`, same pattern as LangGraph/LangChain.

### 5. Python SDK: Runtime Integration

**File:** `sdk/python/src/agentspan/agents/runtime/runtime.py`

Add to `_build_passthrough_func()`:
```python
elif framework == "claude_agent_sdk":
    from agentspan.agents.frameworks.claude_agent_sdk import make_claude_agent_sdk_worker
    return make_claude_agent_sdk_worker(agent_obj, name, server_url, auth_key, auth_secret)
```

No other runtime changes needed — the existing passthrough registration, worker management, and event streaming paths handle everything.

### 6. Java Server: Normalizer

**New file:** `server/src/main/java/dev/agentspan/runtime/normalizer/ClaudeAgentSdkNormalizer.java`

```java
@Component
public class ClaudeAgentSdkNormalizer implements AgentConfigNormalizer {
    @Override public String frameworkId() { return "claude_agent_sdk"; }

    @Override
    public AgentConfig normalize(Map<String, Object> raw) {
        // Extract name and worker name
        // Set metadata._framework_passthrough = true
        // Create single ToolConfig with toolType="worker"
        // Return minimal AgentConfig
    }
}
```

Follows the exact LangChain normalizer pattern. The compiler's `compileFrameworkPassthrough()` produces a WorkflowDef with a single SIMPLE task passing `prompt`, `session_id`, `media`, `cwd` to the worker.

### 7. Use Case C: Claude Agent SDK as Worker Tool

**Phase 1 (ships with use case A):** Users wrap Claude Agent SDK in an agentspan `@tool`:

```python
@tool
async def code_review(prompt: str) -> str:
    """Delegate to Claude Agent SDK code reviewer."""
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep"],
        system_prompt="You are a code reviewer...",
    )
    result = ""
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, "result"):
            result = message.result
    return result
```

Works today with no additional framework changes. The `@tool` runs in a Conductor worker task. Limitation: no SUB_WORKFLOW in Conductor, no streaming events from the inner agent.

**Phase 2 (follow-up):** Add `runtime.register(options, name="...")` method that:
1. Serializes + sends to `/api/agent/compile` to register the agent by name
2. Parent agents reference by name in handoffs: `HandoffCondition(target="claude_reviewer")`
3. Full SUB_WORKFLOW composition with streaming events

## Design Decisions

| Decision | Rationale |
|---|---|
| Passthrough (not extraction) | Claude Agent SDK is a full runtime with built-in tools, hooks, sessions, permissions. Extracting individual tools would lose most of its value and require reimplementing Read/Edit/Bash/etc. as Conductor workers. |
| Hooks for observability | Claude Agent SDK's hook system provides the exact instrumentation points we need. Hooks are additive (don't replace user hooks) and defensive (never crash the agent). |
| `asyncio.run()` in sync worker | Conductor workers are sync functions in ThreadPoolExecutor threads. `asyncio.run()` creates a new event loop — safe because worker threads don't have existing loops. Documented limitation: doesn't work from within an already-running async context (e.g., Jupyter). |
| Options in closure, not JSON | `ClaudeAgentOptions` may contain callables (hooks, custom tools). These can't be JSON-serialized. The closure pattern (same as LangGraph/LangChain) keeps the object in memory. |
| Phase 1 `@tool` for use case C | HandoffCondition.target is a string (agent name), and Agent.agents only accepts Agent instances. A `runtime.register()` method is needed for native sub-agent composition — deferred to Phase 2. |
| User hooks run first | Agentspan hooks are appended after user hooks in each event's matcher list. User logic takes priority. |

## Files Changed

| File | Change |
|---|---|
| `sdk/python/src/agentspan/agents/frameworks/serializer.py` | Add detection + serialize_agent short-circuit |
| `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py` | **New** — serializer, worker, hooks |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | Add `claude_agent_sdk` branch in `_build_passthrough_func()` |
| `server/.../normalizer/ClaudeAgentSdkNormalizer.java` | **New** — passthrough normalizer |

## Dependencies

- `claude-agent-sdk` Python package (optional — lazy import, only loaded when user passes `ClaudeAgentOptions`)
- No new server dependencies

## Testing

- Unit tests for serializer (detection, raw_config shape)
- Unit tests for hook merging (user hooks preserved, agentspan hooks appended)
- Integration test: passthrough execution with a simple Claude Agent SDK agent
- Integration test: verify stream events arrive via SSE
- Integration test: verify task metadata persisted after completion
- Validation example: `sdk/python/examples/claude_agent_sdk/01_basic_agent.py`

## Limitations

- `asyncio.run()` does not work from within an already-running event loop (e.g., Jupyter notebooks). Workaround: use `nest_asyncio` or run from a separate thread.
- Phase 1 use case C (`@tool` wrapper) does not produce a SUB_WORKFLOW or stream inner agent events.
- Hooks capture tool-level events but not individual LLM API calls within the Claude Agent SDK (the SDK doesn't expose an LLM-call hook).
