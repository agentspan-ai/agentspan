# AgentSpan Worker Types

Workers are Python functions registered as Conductor tasks via the `@worker_task` decorator.
They execute locally (SDK-side) while the workflow orchestration happens server-side.

## Quick Reference

| # | Worker Type | Task Name Pattern | Async | Trigger |
|---|-------------|-------------------|-------|---------|
| 1 | Tool | `{tool_name}` | No | `agent.tools` with `tool_type == "worker"` |
| 2 | Output Guardrail (combined) | `{agent_name}_output_guardrail` | Yes | Custom guardrails on agent (local compile path) |
| 3 | Individual Guardrail | `{guardrail.name}` | Yes | Custom guardrails on agent or tool (server compile path) |
| 4 | Stop When | `{agent_name}_stop_when` | Yes | `agent.stop_when` is callable |
| 5 | Gate | `{agent_name}_gate` | Yes | `agent.gate` is callable |
| 6 | Callback | `{agent_name}_{position}` | Yes | `agent.callbacks` or legacy callback attrs |
| 7 | Termination | `{agent_name}_termination` | Yes | `agent.termination` is set |
| 8 | Check Transfer | `{agent_name}_check_transfer` | Yes | Agent has both `tools` and `agents`, or swarm |
| 9 | Router Function | `{agent_name}_router_fn` | Yes | `strategy == "router"` with callable `agent.router` |
| 10 | Handoff Check | `{agent_name}_handoff_check` | Yes | `agent.handoffs` is non-empty |
| 11 | Swarm Transfer Tool | `transfer_to_{peer_name}` | Yes | `strategy == "swarm"` with sub-agents |
| 12 | Manual Selection | `{agent_name}_process_selection` | Yes | `strategy == "manual"` with sub-agents |
| 13 | Framework | `{worker.name}` | No | Foreign framework agents with callable workers |

> **Note:** All system-level workers (#2–#12) are async with `thread_count=10`.
> Tool workers (#1) and framework workers (#13) remain synchronous as they wrap
> user-defined functions directly. User-provided functions (guardrails, callbacks, etc.)
> are called via `_call_user_fn()` which handles both sync and async callables.

## Default Configuration (All Workers)

| Setting              | Value          |
|----------------------|----------------|
| Poll interval        | 100 ms         |
| Thread count         | 10 per worker          |
| Daemon mode          | True           |
| Task timeout         | 120 s          |
| Response timeout     | 120 s          |
| Retry count          | 2              |
| Retry logic          | LINEAR_BACKOFF |
| Retry delay          | 2 s            |
| Timeout policy       | RETRY          |

Source: `_default_task_def()` in `runtime.py`, `WorkerManager.__init__()` in `worker_manager.py`.

---

## 1. Tool Worker

| Field          | Value                    |
|----------------|--------------------------|
| Task name      | `{tool_name}`            |
| Async          | No                       |
| Trigger        | `agent.tools` with `tool_type == "worker"` |
| Registered by  | `ToolRegistry.register_tool_workers()` |

Executes `@tool`-decorated Python functions. Each tool gets its own Conductor task definition.
Tool-level guardrails are applied inline by the `make_tool_worker()` wrapper.
HTTP and MCP tools are server-side and do not get a local worker.

---

## 2. Output Guardrail Worker (combined)

| Field          | Value                              |
|----------------|------------------------------------|
| Task name      | `{agent_name}_output_guardrail`    |
| Async          | Yes                                |
| Trigger        | `agent.guardrails` has custom (non-Regex/LLM/external) functions |
| Registered by  | `_register_guardrail_worker()`     |

Runs all of an agent's custom guardrails sequentially on agent output.
Used by the local compilation path. Server-side compilation uses individual guardrail workers instead.

---

## 3. Individual Guardrail Worker

| Field          | Value                     |
|----------------|---------------------------|
| Task name      | `{guardrail.name}`        |
| Async          | Yes                       |
| Trigger        | Each custom guardrail with `func is not None` and not Regex/LLM/external |
| Registered by  | `_register_single_guardrail_worker()` |

Runs a single guardrail function. Used by server-side compilation where each guardrail is a separate SIMPLE task.

**Inputs:** `content` (object), `iteration` (int)
**Returns:** `{ passed, message, on_fail, fixed_output, guardrail_name, should_continue }`

---

## 4. Stop When Worker

| Field          | Value                        |
|----------------|------------------------------|
| Task name      | `{agent_name}_stop_when`     |
| Async          | Yes                          |
| Trigger        | `agent.stop_when` is callable |
| Registered by  | `_register_stop_when_worker()` |

Evaluates a custom stop-condition callback to decide whether iteration should end.

**Inputs:** `result` (str), `iteration` (int)
**Returns:** `{ should_continue }` (bool)

---

## 5. Gate Worker

| Field          | Value                    |
|----------------|--------------------------|
| Task name      | `{agent_name}_gate`      |
| Async          | Yes                      |
| Trigger        | `agent.gate` is callable  |
| Registered by  | `_register_gate_worker()` |

Conditional gating for sequential pipelines. Called between stages to decide whether to continue or stop.

**Inputs:** `result` (str)
**Returns:** `{ decision }` ("continue" or "stop")

---

## 6. Callback Workers

| Field          | Value                                |
|----------------|--------------------------------------|
| Task name      | `{agent_name}_{position}`            |
| Async          | Yes                                  |
| Trigger        | `agent.callbacks` or legacy callback attrs |
| Registered by  | `_register_callback_worker()`        |

Lifecycle hooks at six execution points:

| Position         | Legacy attribute          |
|------------------|---------------------------|
| `before_agent`   | `before_agent_callback`   |
| `after_agent`    | `after_agent_callback`    |
| `before_model`   | `before_model_callback`   |
| `after_model`    | `after_model_callback`    |
| `before_tool`    | —                         |
| `after_tool`     | —                         |

Multiple callbacks per position are chained; the first non-empty dict returned wins.

---

## 7. Termination Worker

| Field          | Value                            |
|----------------|----------------------------------|
| Task name      | `{agent_name}_termination`       |
| Async          | Yes                              |
| Trigger        | `agent.termination` is set       |
| Registered by  | `_register_termination_worker()` |

Evaluates a TerminationCondition to decide if the agent should stop.

**Inputs:** `result` (str), `iteration` (int)
**Returns:** `{ should_continue, reason }`

---

## 8. Check Transfer Worker

| Field          | Value                              |
|----------------|------------------------------------|
| Task name      | `{agent_name}_check_transfer`      |
| Async          | Yes                                |
| Trigger        | Agent has both `tools` and `agents` (hybrid handoff), or swarm strategy |
| Registered by  | `_register_check_transfer_worker()` |

Inspects tool calls for `transfer_to_*` function names to detect handoff requests.

**Inputs:** `tool_calls` (list of dicts)
**Returns:** `{ is_transfer, transfer_to }`

For swarm agents, registered for the parent and every sub-agent.

---

## 9. Router Function Worker

| Field          | Value                          |
|----------------|--------------------------------|
| Task name      | `{agent_name}_router_fn`       |
| Async          | Yes                            |
| Trigger        | `strategy == "router"` and `agent.router` is callable (no `.model` attr) |
| Registered by  | `_register_router_worker()`    |

Calls a user-provided Python function to select which sub-agent handles the prompt.
LLM-based routers are server-side and do not get a local worker.

**Inputs:** `prompt` (str)
**Returns:** `{ selected_agent }` (agent name)

---

## 10. Handoff Check Worker

| Field          | Value                            |
|----------------|----------------------------------|
| Task name      | `{agent_name}_handoff_check`     |
| Async          | Yes                              |
| Trigger        | `agent.handoffs` is non-empty    |
| Registered by  | `_register_handoff_worker()`     |

Determines if and where to handoff in swarm strategies. Supports two mechanisms:

1. **Transfer tool** — primary: `is_transfer=true, transfer_to=<name>`
2. **Condition-based** — secondary: `OnTextMention`, `OnCondition`, etc.

Respects `agent.allowed_transitions` constraints and tracks consecutive blocked transfers (max 3).

**Inputs:** `result`, `active_agent`, `conversation`, `is_transfer`, `transfer_to`
**Returns:** `{ active_agent, handoff }`

---

## 11. Swarm Transfer Tools

| Field          | Value                          |
|----------------|--------------------------------|
| Task name      | `transfer_to_{peer_name}`      |
| Async          | Yes                            |
| Trigger        | `strategy == "swarm"` with sub-agents |
| Registered by  | `_register_swarm_transfer_workers()` |

No-op tools that let the LLM express a handoff intent. The actual handoff is detected by the check_transfer worker.
One tool per unique target name across the swarm (deduplicated).

Returns `{}` normally, or an error string if `allowed_transitions` prevents that transfer.

---

## 12. Manual Selection Worker

| Field          | Value                                |
|----------------|--------------------------------------|
| Task name      | `{agent_name}_process_selection`     |
| Async          | Yes                                  |
| Trigger        | `strategy == "manual"` with sub-agents |
| Registered by  | `_register_manual_selection_worker()` |

Processes human input to select which sub-agent to run.

**Inputs:** `human_output` (object)
**Returns:** `{ selected }` (agent index as string)

---

## 13. Framework Workers

| Field          | Value                     |
|----------------|---------------------------|
| Task name      | `{worker.name}`           |
| Async          | No                        |
| Trigger        | Foreign framework agents with callable workers |
| Registered by  | `_register_framework_workers()` |

Bridges callable workers extracted from non-AgentSpan frameworks (e.g. CrewAI, LangGraph)
into Conductor tasks. Uses the same `make_tool_worker()` wrapper as tool workers.

---

## Worker Lifecycle

1. **Registration** — `_register_workers()` recursively walks the agent tree and calls the appropriate `_register_*_worker()` methods. Each calls `@worker_task` which adds the function to the global `_decorated_functions` dict.

2. **Start** — `WorkerManager.start()` creates a `TaskHandler` with `scan_for_annotated_workers=True`, which reads `_decorated_functions` and forks a process per worker.

3. **Incremental addition** — When new agents introduce new worker types, `_start_new_workers()` injects them into the running TaskHandler without stopping existing workers.

4. **Monitoring** — The TaskHandler monitor thread checks process health every 5 seconds and restarts dead workers with exponential backoff.

5. **Shutdown** — `WorkerManager.stop()` is only called during `AgentRuntime.shutdown()`.
