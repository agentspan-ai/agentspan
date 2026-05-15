# `_state_updates` Protocol — Tool State Persistence

This document describes how tool state mutations persist across agent turns. SDK implementors **must** follow this protocol for tools that use `ToolContext.state`.

## Overview

Tools can read and write per-agent state via `ToolContext.state` (a `Dict[str, Any]`). Mutations made during a tool call are captured by the SDK dispatch layer, propagated through the Conductor workflow, and persisted as a workflow variable. On subsequent turns, the accumulated state is injected back into every tool call.

## Round-Trip Flow

```
Tool mutates context.state
  ↓
SDK dispatch wraps output with _state_updates
  ↓
Conductor FORK/JOIN: JOIN propagates _state_updates (compact output)
  ↓
merge_state (INLINE task): extracts _state_updates from JOIN output
  ↓
SET_VARIABLE: deep-merges into _agent_state workflow variable
  ↓
ctx_inject (INLINE task): reads _agent_state, prepends to LLM prompt
  ↓
Next tool call: _agent_state injected into task input_data
  ↓
SDK dispatch extracts _agent_state → populates ToolContext.state
```

## SDK Responsibilities

### 1. Inject `_agent_state` into ToolContext

When a tool task arrives from Conductor, extract `_agent_state` from `task.input_data` and use it to populate `ToolContext.state`:

```python
# Python reference (sdk/python/src/agentspan/agents/runtime/_dispatch.py)
agent_state = task.input_data.pop("_agent_state", None) or {}
ctx = ToolContext(state=dict(agent_state), ...)
```

Key points:
- Pop `_agent_state` from input data so it doesn't appear as a tool argument
- Copy the dict (don't share the reference)
- Default to empty dict if absent

### 2. Capture State Mutations in Tool Output

After the tool function returns, check if `ToolContext.state` has any entries and wrap them into the tool output under the `_state_updates` key:

```python
# Python reference (sdk/python/src/agentspan/agents/runtime/_dispatch.py, lines 388-394)
if ctx is not None and ctx.state:
    state_updates = dict(ctx.state)
    if isinstance(result, dict):
        result["_state_updates"] = state_updates
    else:
        result = {"result": result, "_state_updates": state_updates}
```

Key points:
- Only add `_state_updates` if `ctx.state` is non-empty
- If the tool result is already a dict, add the key inline
- If the tool result is a scalar/string, wrap it in `{"result": <original>, "_state_updates": ...}`
- The value of `_state_updates` is the **full** state dict, not a delta

### 3. Strip `_agent_state` from User-Facing Events

When emitting `tool_call` events to the user (SSE stream), strip `_agent_state` from the displayed arguments so internal state doesn't leak into the user-facing event stream:

```python
# Python reference (sdk/python/src/agentspan/agents/result.py, AgentEvent)
_INTERNAL_ARG_KEYS = frozenset({"_agent_state", "method"})
```

## Server-Side Handling (Reference Only)

SDK implementors don't need to modify server code, but understanding the server side helps:

1. **JOIN task** (`server/.../tasks/Join.java`): Only propagates `_state_updates` and `state` keys from fork outputs — NOT full tool results.

2. **merge_state** (GraalJS INLINE task): Reads `_state_updates` from JOIN output, deep-merges into the `_agent_state` workflow variable via `SET_VARIABLE`.

3. **ctx_inject** (GraalJS INLINE task): Reads the `_agent_state` variable and formats it as a JSON context block prepended to the LLM prompt.

4. **Tool input enrichment**: The server injects the current `_agent_state` into every tool task's `input_data` before dispatch.

## Testing

The e2e test at `sdk/python/tests/integration/test_e2e_state_updates.py` validates:

1. **Positive**: A tool that sets `context.state["test_counter"] = 42` → verify `_agent_state` workflow variable contains `{"test_counter": 42}` after execution.

2. **Counterfactual**: A tool that does NOT mutate state → verify `_agent_state` is empty/absent.

Both use algorithmic assertions against the Conductor workflow API — no LLM output validation.

## Example: Python Tool with State

```python
from agentspan.agents import tool
from agentspan.agents.tool import ToolContext

@tool
def track_files_read(path: str, context: ToolContext) -> str:
    """Read a file and track which files have been read."""
    # Read accumulated state from previous turns
    files_read = context.state.get("files_read", [])

    content = open(path).read()

    # Mutate state — SDK captures this automatically
    files_read.append(path)
    context.state["files_read"] = files_read
    context.state["total_files"] = len(files_read)

    return content
```

On the next turn, `context.state` will contain `{"files_read": ["file1.py"], "total_files": 1}` — the server persisted and re-injected it.
