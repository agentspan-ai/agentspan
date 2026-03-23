# Conductor Agents SDK — Design Document

## Overview

The `agentspan-sdk` SDK defines Python `Agent` objects that are compiled into durable Conductor workflows by the server-side Java compiler. This document describes the internal architecture, compilation model, and key design decisions.

## Design Principles

1. **Everything is an Agent.** One primitive for single agents, multi-agent teams, and nested hierarchies. No Team, Network, or Swarm classes.

2. **Server-first execution.** Tools execute as distributed Conductor tasks, not in-process. The agent survives process crashes. Human approvals can take days.

3. **Compile, don't interpret.** Agent definitions are compiled into static Conductor workflow JSON by the server. The runtime just executes the workflow. This means agent behavior is inspectable, versioned, and reproducible.

4. **Zero config for simple cases.** `Agent + tool + run` works in 5 lines. Advanced features (memory, guardrails, streaming) layer on without changing the core API.

5. **Conductor-native.** Every SDK concept maps directly to a Conductor primitive. No abstraction layer that hides what's happening.

---

## Architecture

### Compilation Pipeline

```
User Code          Python SDK                 Java Server
==========         ==========                 ===========

Agent(             AgentConfigSerializer      AgentCompiler
  name,              .serialize()               .compile()
  model,                |                         |
  tools,                v                         v
  agents,          JSON payload  ──POST──>   Workflow Definition (JSON)
  ...              /agent/compile             stored on server
)
                   ToolRegistry               Task Definitions
                     .register_tool_workers()   registered
                        |
                        v
                   Worker functions     --->  Worker task registered
                   registered via                via @worker_task
                   _tool_registry
```

### Runtime Lifecycle

```
run(agent, prompt)
    |
    v
AgentRuntime (singleton)
    |
    +-- _compile_agent(agent)     # cached per agent.name
    |     |
    |     +-- _compile_via_server(agent)
    |     |     |
    |     |     +-- AgentConfigSerializer.serialize(agent)
    |     |     +-- POST /agent/compile  (JSON payload)
    |     |     +-- Server-side Java AgentCompiler handles dispatch:
    |     |           agent.agents and not agent.tools? --> MultiAgentCompiler
    |     |           agent.agents and agent.tools?     --> _compile_hybrid()
    |     |           agent.tools?                      --> _compile_with_tools()
    |     |           no tools?                         --> _compile_simple()
    |     |
    |     +-- Returns ServerCompiledWorkflow
    |
    +-- _prepare(agent)
    |     |
    |     +-- ToolRegistry.register_tool_workers()  # register Python workers
    |     +-- WorkerManager.start()  # long-lived, not per-call
    |
    +-- wf.execute(workflow_input={prompt, session_id})
    |
    +-- _extract_output(workflow_run, agent)
    |     |
    |     +-- Parse structured output (Pydantic) if output_type set
    |     +-- Extract handoff result from nested dict
    |
    +-- Return AgentResult
```

### Singleton Runtime

The `run()`, `start()`, `stream()`, and `run_async()` functions share a module-level singleton `AgentRuntime`. This avoids creating new Conductor clients and worker processes on every call:

```python
# Module: run.py
_default_runtime = None  # created on first use, thread-safe
atexit.register(_shutdown_default_runtime)  # graceful shutdown

def run(agent, prompt, *, runtime=None, **kwargs):
    rt = runtime or _get_default_runtime()
    return rt.run(agent, prompt, **kwargs)
```

Workers are started once and run until process exit (not stopped after each call).

---

## Compiled Workflow Structures

### Single Agent with Tools (DoWhile Loop)

```
[SetVariable: init messages]
    |
    v
[DoWhile]
    |
    +-- [LlmChatComplete] -- reads ${workflow.variables.messages}
    |       json_output=True
    |
    +-- [dispatch_worker] -- routes tool calls, updates messages
    |       llm_response=${llm.output.result}
    |       messages=${workflow.variables.messages}
    |
    +-- [SetVariable: update messages]
    |       messages=${dispatch.output.messages}
    |
    +-- [stop_when_worker] (optional)
    |       if agent.stop_when is set
    |
    condition: $.loop.iteration < max_turns
               && $.dispatch.continue_loop == true
               [&& $.stop_when.should_continue == true]
    |
    v
Output: ${dispatch.output.result}
```

**Key detail:** In Conductor DoWhile conditions, task references map directly to outputData (no `.output` wrapper): `$.dispatch.continue_loop`, NOT `$.dispatch.output.continue_loop`.

### Single Agent (No Tools)

```
[LlmChatComplete]
    messages=[system_prompt, user_prompt]
    |
    v
Output: ${llm.output.result}
```

### Handoff Strategy

```
[LlmChatComplete: router]
    "Which sub-agent should handle this?"
    |
    v
[SwitchTask]
    case "billing"   --> [InlineSubWorkflow: agent_billing]
    case "technical"  --> [InlineSubWorkflow: agent_technical]
    default           --> [InlineSubWorkflow: first_agent]
    |
    v
Output: {billing: result_or_null, technical: result_or_null}
```

### Sequential Strategy

```
[SubWorkflow: agent_step_0] -- prompt = ${workflow.input.prompt}
    |
    v
[SubWorkflow: agent_step_1] -- prompt = ${step_0.output.result}
    |
    v
[SubWorkflow: agent_step_2] -- prompt = ${step_1.output.result}
    |
    v
Output: ${step_2.output.result}
```

### Parallel Strategy

```
[ForkTask]
    |
    +-- [SubWorkflow: agent_analyst_0]  -- prompt = ${workflow.input.prompt}
    |
    +-- [SubWorkflow: agent_analyst_1]  -- prompt = ${workflow.input.prompt}
    |
    +-- [SubWorkflow: agent_analyst_2]  -- prompt = ${workflow.input.prompt}
    |
[JoinTask]
    |
    v
Output: {analyst_0: result, analyst_1: result, analyst_2: result}
```

### Router Strategy

**Agent-based router:**
```
[LlmChatComplete: router_agent's model/instructions]
    |
    v
[SwitchTask]
    case "planner" --> [InlineSubWorkflow: agent_planner]
    case "coder"   --> [InlineSubWorkflow: agent_coder]
```

**Function-based router:**
```
[router_worker: registered Python function]
    prompt=${workflow.input.prompt}
    |
    v
[SwitchTask]
    case_expression=${router.output.selected_agent}
```

### Hybrid (Tools + Sub-Agents)

```
[SetVariable: init messages with transfer_to_{name} tool descriptions]
    |
    v
[DoWhile: standard tool loop]
    LLM can call regular tools OR transfer_to_{name}
    |
    v
[SwitchTask: check if last function was a transfer]
    case "transfer_to_specialist" --> [InlineSubWorkflow: agent_specialist]
    default                        --> (direct result)
    |
    v
Output: {direct: result, specialist: result_or_null}
```

---

## Dispatch Worker

The `dispatch_worker` is the universal tool execution router. It runs as a Conductor worker task and processes each LLM response:

### Flow

```
LLM Response
    |
    v
Parse (fuzzy: strip markdown fences, extract JSON, normalize keys)
    |
    v
Is it a tool call (type == "function")?
    |
    +-- No  --> Final answer: continue_loop=False, result=text
    |
    +-- Yes --> Check circuit breaker (3 consecutive failures?)
                |
                +-- Tripped --> Error message, continue_loop=True
                |
                +-- OK --> Check approval_required?
                           |
                           +-- Yes --> needs_approval=True, continue_loop=False
                           |
                           +-- No --> Execute tool function
                                      |
                                      +-- Inject ToolContext if declared
                                      +-- Append result to messages
                                      +-- continue_loop=True
```

### Key Design Choices

**`object` type annotations:** The dispatch worker uses `object` for `llm_response` and `messages` parameters (not `dict`/`list`) because Conductor's worker framework calls `convert_from_dict_or_list()` on non-simple types, and bare `list`/`dict` crash with `IndexError` on `typing.get_args()`.

**No `from __future__ import annotations`:** The file deliberately avoids this because Conductor's worker framework needs real type objects (not strings) for parameter type resolution at runtime.

**Global registries:** Tool functions, error counts, and approval flags are stored in module-level dicts (`_tool_registry`, `_tool_error_counts`, `_tool_approval_flags`). This is necessary because the dispatch worker function is shared across all agents and registered once per task name.

---

## Guardrail Compilation

Guardrails run in two locations:

1. **Input guardrails** — Checked in `AgentRuntime.run()` before workflow execution. If `on_fail="raise"`, raises `ValueError`. This is a runtime check, not compiled into the workflow.

2. **Output guardrails** — Compiled into the DoWhile loop as durable workflow tasks. Local guardrails are bundled into a combined worker task; external guardrails (referenced by name, no local function) are compiled as individual `SimpleTask` nodes referencing the remote worker. After each guardrail task, a `SwitchTask` routes on the result: retry (append feedback + continue loop), raise (terminate), fix (use corrected output), or human (HumanTask escalation).

### API surface

The `@guardrail` decorator, `OnFail` / `Position` enums, and `GuardrailDef` dataclass provide a typed, discoverable API:

```python
from agentspan.agents import guardrail, Guardrail, GuardrailResult, OnFail, Position

@guardrail
def no_pii(content: str) -> GuardrailResult:
    ...

agent = Agent(
    guardrails=[Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY)],
)

# External guardrail — worker runs in another service
agent = Agent(
    guardrails=[Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)],
)
```

Plain strings (`"retry"`, `"output"`) remain fully backward-compatible since the enums are `str` subclasses.

---

## Streaming

The `stream()` method polls the Conductor workflow with `include_tasks=True` and tracks seen task IDs. New/changed tasks generate typed events:

| Task Type | Condition | Event |
|---|---|---|
| `LLM_CHAT_COMPLETE` | New task | `THINKING` |
| Dispatch (SIMPLE) | Completed with `function` in output | `TOOL_CALL` + `TOOL_RESULT` |
| `SUB_WORKFLOW` | New task | `HANDOFF` |
| Any | Status=FAILED | `ERROR` |
| Workflow | Status=PAUSED | `WAITING` |
| Workflow | Status=COMPLETED | `DONE` |

Poll interval: 500ms.

---

## Configuration Hierarchy

```
Environment Variables (AGENTSPAN_*)
    |
    v
AgentConfig (dataclass)
    |
    +-- server_url, auth_key, auth_secret
    +-- default_timeout_seconds (300)
    +-- llm_retry_count (3)
    +-- worker_poll_interval_ms (100)
    +-- worker_thread_count (1)
    +-- auto_register_workflows (True)
    +-- auto_start_workers (True)
    |
    v
AgentRuntime
    |
    +-- sends config to server for compilation
    |     +-- timeout, retry count, etc. serialized in agent config JSON
    |
    +-- passes config to ToolRegistry (worker registration)
    +-- passes config to WorkerManager
```

---

## Logging

Every module uses `logging.getLogger("agentspan.agents.xxx")`:

| Logger | Key Events |
|---|---|
| `agentspan.agents.runtime` | Workflow start/complete, worker start/stop, guardrail pass/fail |
| `agentspan.agents.dispatch` | Tool calls, tool results, circuit breaker, approval signals |
| `agentspan.agents.runtime.tool_registry` | Tool registration, approval flags |
| `agentspan.agents.runtime.mcp_discovery` | MCP tool discovery |
| `agentspan.agents.worker_manager` | Worker process lifecycle |
| `agentspan.agents.run` | Singleton creation/shutdown |

Enable with:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Testing Strategy

### Unit Tests (766 tests, no server required)

| File | Scope |
|---|---|
| `test_agent.py` | Agent creation, validation, chaining, repr |
| `test_tool.py` | @tool, http_tool, mcp_tool, get_tool_def, @worker_task |
| `test_compiler.py` | Model parser, schema generation |
| `test_dispatch.py` | Core dispatch: tool calls, final answers, errors, compat |
| `test_dispatch_advanced.py` | Fuzzy parsing, circuit breaker, approval, trimming, ToolContext |
| `test_runtime.py` | extract_output, extract_handoff, singleton, config |
| `test_guardrail.py` | Guardrail creation, validation, check |
| `test_memory.py` | ConversationMemory: add, trim, clear, pre-populate |
| `test_result.py` | AgentResult, AgentStatus, AgentEvent, EventType |
| `test_mcp_discovery.py` | MCP tool discovery |
| `test_new_features.py` | New feature tests |

### Integration Tests (require running Conductor server)

Located in `tests/integration/`. Test end-to-end agent execution against a live server.

### CI/CD

`.github/workflows/ci.yml` runs on push/PR to main:
- Unit tests on Python 3.9-3.13
- Lint with ruff
- Type check with mypy
