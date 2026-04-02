# Agent(model="claude-code") API Design

**Date:** 2026-03-27
**Status:** Draft
**Depends on:** Claude Agent SDK passthrough integration (completed)

## Overview

Add a consistent `Agent(model="claude-code/opus")` API so Claude Agent SDK agents use the same `Agent(...)` interface as native agents, enabling multi-agent composition, handoffs, and all orchestration patterns.

## Goals

- Users define Claude Code agents using `Agent(...)` — no new classes to learn
- Claude Code agents work as sub-agents in `Agent(agents=[...])`
- Claude Code agents work with handoffs, sequential, parallel, router patterns
- Minimal API surface on `ClaudeCode` config: model name + permission mode only

## API

```python
from agentspan.agents import Agent

# Simple — slash syntax
reviewer = Agent(
    name="reviewer",
    model="claude-code/opus",
    instructions="Review Python code for quality and security",
    tools=["Read", "Glob", "Grep"],
    max_turns=10,
)

# Default model (CLI default)
reviewer = Agent(name="reviewer", model="claude-code", instructions="...", tools=["Read"])

# With config object for permission_mode
from agentspan.agents import ClaudeCode

reviewer = Agent(
    name="reviewer",
    model=ClaudeCode("opus", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    instructions="Review code",
    tools=["Read", "Edit", "Bash"],
    max_turns=10,
)

# Multi-agent
pipeline = Agent(
    name="pipeline",
    model="anthropic/claude-sonnet-4-5",
    agents=[reviewer, writer, tester],
    strategy="sequential",
)

# Handoffs
Agent(
    name="analyst",
    model="anthropic/claude-sonnet-4-5",
    handoffs=[HandoffCondition(target="reviewer", condition="needs review")],
)
```

## `ClaudeCode` Config

```python
from enum import Enum
from dataclasses import dataclass

@dataclass
class ClaudeCode:
    """Configuration for Agent(model=ClaudeCode(...))."""

    class PermissionMode(str, Enum):
        DEFAULT = "default"
        ACCEPT_EDITS = "acceptEdits"
        PLAN = "plan"
        BYPASS = "bypassPermissions"

    model_name: str = ""          # "opus", "sonnet", "haiku", or full ID
    permission_mode: PermissionMode = PermissionMode.ACCEPT_EDITS
```

- `model_name`: short alias ("opus", "sonnet") or full model ID ("claude-opus-4-6"). Empty = CLI default.
- `permission_mode`: enum, defaults to ACCEPT_EDITS (sensible for automated agents).
- No `mcp_servers` — use `@tool` functions in Phase 2 (MCP bridge) or `ClaudeCodeOptions` escape hatch.
- No `hooks` — agentspan injects observability hooks internally. Use guardrails for user-facing customization.

## Model String Resolution

| Input | Resolved model |
|---|---|
| `"claude-code"` | `None` (CLI default) |
| `"claude-code/opus"` | `"claude-opus-4-6"` |
| `"claude-code/sonnet"` | `"claude-sonnet-4-6"` |
| `"claude-code/haiku"` | `"claude-haiku-4-5"` |
| `"claude-code/claude-opus-4-6"` | `"claude-opus-4-6"` (passthrough) |
| `ClaudeCode("opus")` | `"claude-opus-4-6"` |
| `ClaudeCode()` | `None` (CLI default) |

Resolution function maps short aliases to full model IDs. Unknown aliases are passed through as-is.

## Architecture: Where Config Lives

**Key principle:** The server only sees a passthrough stub. ALL agent configuration (instructions, tools, max_turns, permission_mode) is consumed locally in the Python worker closure. The server's role is to create a minimal workflow with a single SIMPLE task — the worker does the rest.

This means:
- `serialize_claude_agent_sdk()` produces a minimal `{name, _worker_name}` raw_config (same for Agent and ClaudeCodeOptions)
- `_build_passthrough_func()` converts Agent → `ClaudeCodeOptions` dataclass → `make_claude_agent_sdk_worker()` closure
- The closure captures the full `ClaudeCodeOptions` in memory, not in JSON
- `make_claude_agent_sdk_worker()` receives a real `ClaudeCodeOptions` dataclass (never an Agent) — this is critical because `_merge_hooks` calls `dataclasses.replace()` which would crash on a non-dataclass

## Implementation

### 1. `ClaudeCode` dataclass + model resolution

**New file:** `sdk/python/src/agentspan/agents/claude_code.py` (flat in agents package, not a sub-package)

Contains `ClaudeCode` dataclass and `resolve_claude_code_model(alias) -> str | None` dict-based lookup.

Re-exported from `agentspan.agents.__init__`.

### 2. `Agent.__init__` change

Accept `model` as `str | ClaudeCode`:
- If `ClaudeCode` instance: store as `self._claude_code_config`, set `self.model = "claude-code/{model_name}"` string (or `"claude-code"` if no model_name). **`self.model` is NEVER set to `None` or empty string for claude-code agents** — this prevents the `external` property from incorrectly returning `True`.
- If string starting with `"claude-code"`: store `self._claude_code_config = None` (config parsed from string when needed)
- Otherwise: existing behavior unchanged

Add property `Agent.is_claude_code -> bool` that checks `self.model.startswith("claude-code")`.

Validate tools: if `is_claude_code`, all tools must be strings. Custom `@tool` callables raise `ValueError("Claude Code agents only support built-in string tools like 'Read', 'Edit', 'Bash'. Custom @tool functions are not supported yet (Phase 2).")`.

Also update `@agent` decorator: change `AgentDef.model` type from `str` to `Union[str, Any]` so `@agent(model=ClaudeCode("opus"))` works. Update `_resolve_agent` to handle `ClaudeCode` in the `resolved_model` fallback logic.

### 3. Routing: `detect_framework()` change

Currently returns `None` for all `Agent` instances. Change to:

```python
if isinstance(agent_obj, Agent):
    if getattr(agent_obj, 'model', '').startswith("claude-code"):
        return "claude_agent_sdk"
    return None
```

This routes claude-code Agents through the existing framework passthrough path (`_run_framework` / `_start_framework`).

### 4. Serialization: `serialize_claude_agent_sdk()` change

Handle both Agent and ClaudeCodeOptions:

```python
def serialize_claude_agent_sdk(agent_or_options: Any) -> Tuple[Dict, List[WorkerInfo]]:
    from agentspan.agents.agent import Agent

    if isinstance(agent_or_options, Agent):
        name = agent_or_options.name
    else:
        name = _extract_name(agent_or_options)  # Existing path for ClaudeCodeOptions

    raw_config = {"name": name, "_worker_name": name}
    worker = WorkerInfo(name=name, description=f"Claude Agent SDK passthrough worker for {name}",
                        input_schema={...}, func=None)
    return raw_config, [worker]
```

The serializer output is intentionally minimal — it only carries `name` and `_worker_name`. All real config mapping happens in step 5.

### 5. Worker building: `_build_passthrough_func()` change (CRITICAL)

**`make_claude_agent_sdk_worker()` MUST receive a `ClaudeCodeOptions` dataclass, never an Agent.** The worker calls `_merge_hooks()` which calls `dataclasses.replace(options, hooks=merged)` — this crashes on non-dataclass objects.

Add `agent_to_claude_code_options()` in `claude_agent_sdk.py`:

```python
def agent_to_claude_code_options(agent: Any) -> Any:
    """Convert an Agent(model="claude-code/...") to a ClaudeCodeOptions dataclass."""
    from claude_code_sdk import ClaudeCodeOptions
    from agentspan.agents.claude_code import resolve_claude_code_model

    # Resolve model alias
    model_str = getattr(agent, 'model', '') or ''
    _, _, alias = model_str.partition('/')
    resolved_model = resolve_claude_code_model(alias) if alias else None

    # Get permission_mode from _claude_code_config if present
    cc_config = getattr(agent, '_claude_code_config', None)
    permission_mode = getattr(cc_config, 'permission_mode', None) if cc_config else None

    # Resolve instructions to string
    instructions = agent.instructions
    if callable(instructions):
        instructions = instructions()

    return ClaudeCodeOptions(
        allowed_tools=list(agent.tools) if agent.tools else [],
        system_prompt=str(instructions) if instructions else None,
        max_turns=agent.max_turns,
        model=resolved_model,
        permission_mode=permission_mode.value if permission_mode else "acceptEdits",
    )
```

In `_build_passthrough_func()` (both sync and async paths):

```python
elif framework == "claude_agent_sdk":
    from agentspan.agents.frameworks.claude_agent_sdk import (
        make_claude_agent_sdk_worker, agent_to_claude_code_options
    )
    from agentspan.agents.agent import Agent

    # CRITICAL: convert Agent → ClaudeCodeOptions before passing to worker
    if isinstance(agent_obj, Agent):
        options = agent_to_claude_code_options(agent_obj)
    else:
        options = agent_obj  # Already ClaudeCodeOptions

    return make_claude_agent_sdk_worker(options, name, server_url, auth_key, auth_secret)
```

### 6. Sub-agent support: `_prepare_workers` + `config_serializer` + server

Three coordinated changes required:

**6a. `_prepare_workers()` in runtime.py** — guard against claude-code sub-agents:

When recursing into sub-agents, detect `is_claude_code` and register a passthrough worker instead of recursing into tools (which would crash on string tool names):

```python
for sub_agent in agent.agents:
    if sub_agent.is_claude_code:
        # Register passthrough worker for this sub-agent
        options = agent_to_claude_code_options(sub_agent)
        worker_func = make_claude_agent_sdk_worker(options, sub_agent.name, ...)
        # Register via _register_passthrough_worker
        ...
    else:
        self._prepare_workers(sub_agent)  # Normal recursive path
```

**6b. `config_serializer._serialize_agent()`** — emit passthrough metadata for claude-code sub-agents:

When serializing a sub-agent with `is_claude_code`, emit:
```python
{
    "name": sub_agent.name,
    "model": sub_agent.model,
    "metadata": {"_framework_passthrough": True},
    "tools": [{"name": sub_agent.name, "toolType": "worker", "description": "Claude Agent SDK passthrough worker"}],
    # DO NOT serialize instructions, tools list, etc. — those are consumed by the worker
}
```

This matches the shape that `ClaudeAgentSdkNormalizer` produces.

**6c. `AgentCompiler.compileSubAgent()` (Java)** — detect claude-code model prefix:

```java
if (subConfig.getModel() != null && subConfig.getModel().startsWith("claude-code")) {
    // Override: force passthrough compilation
    if (subConfig.getMetadata() == null) subConfig.setMetadata(new LinkedHashMap<>());
    subConfig.getMetadata().put("_framework_passthrough", true);
}
```

Then the existing `compileFrameworkPassthrough()` path handles it. This is a safety net — the Python SDK should already set the metadata correctly (6b), but the server validates.

### 7. Async path

The same `detect_framework` change and `_build_passthrough_func` change apply to the async paths:
- `_run_framework_async()` (line ~3845)
- `_start_framework_async()` (line ~3947)
- `_build_passthrough_func()` is shared between sync and async — only one change needed there

### 8. Examples

- `sdk/python/examples/claude_agent_sdk/02_multi_agent_router.py` — orchestrator routes to Claude Code sub-agents
- `sdk/python/examples/claude_agent_sdk/03_sequential_pipeline.py` — reviewer → writer → tester pipeline
- `sdk/python/examples/claude_agent_sdk/04_handoff.py` — analyst hands off to Claude Code reviewer

## What Stays the Same

- `runtime.run(ClaudeCodeOptions(...))` — still works as escape hatch
- `make_claude_agent_sdk_worker()` — unchanged (always receives ClaudeCodeOptions)
- `_build_agentspan_hooks()` — unchanged
- `ClaudeAgentSdkNormalizer` — unchanged (handles the passthrough raw_config)
- Event push, credential injection — unchanged

## Files Changed

| File | Change |
|---|---|
| `sdk/python/src/agentspan/agents/claude_code.py` | **New** — ClaudeCode dataclass, model resolution, PermissionMode enum |
| `sdk/python/src/agentspan/agents/__init__.py` | **Modify** — re-export ClaudeCode |
| `sdk/python/src/agentspan/agents/agent.py` | **Modify** — accept ClaudeCode in model, add is_claude_code, validate string tools, update @agent decorator |
| `sdk/python/src/agentspan/agents/frameworks/serializer.py` | **Modify** — detect_framework returns "claude_agent_sdk" for claude-code Agents |
| `sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py` | **Modify** — handle Agent in serializer, add agent_to_claude_code_options() |
| `sdk/python/src/agentspan/agents/runtime/runtime.py` | **Modify** — _build_passthrough_func converts Agent→ClaudeCodeOptions, _prepare_workers guards claude-code sub-agents |
| `sdk/python/src/agentspan/agents/config_serializer.py` | **Modify** — emit passthrough metadata for claude-code sub-agents |
| `server/.../compiler/AgentCompiler.java` | **Modify** — detect claude-code model prefix in sub-agent compilation |
| `sdk/python/examples/claude_agent_sdk/02_multi_agent_router.py` | **New** |
| `sdk/python/examples/claude_agent_sdk/03_sequential_pipeline.py` | **New** |
| `sdk/python/examples/claude_agent_sdk/04_handoff.py` | **New** |
| Tests for each changed file | **New/Modify** |

## Limitations

- Phase 1: only string tools (Claude built-in) work with `model="claude-code"`. Custom `@tool` functions raise `ValueError`.
- Phase 2 (future): MCP bridge auto-converts `@tool` functions to MCP servers.
- `ClaudeCodeOptions` escape hatch available for power users who need raw MCP, hooks, etc.
