# API reference

The public surface, importable from `conductor.ai.agents` unless noted. This is a
reference; for usage see [Writing agents](writing-agents.md), [Framework
agents](framework-agents.md), and [Advanced](advanced.md).

- [AgentRuntime](#agentruntime)
- [Agent / @agent](#agent)
- [Tools](#tools) and [built-in tools](#built-in-tools)
- [Guardrails](#guardrails)
- [Termination](#termination)
- [Handoffs](#handoffs)
- [TextGate](#textgate)
- [Schedules](#schedules)
- [Results, handles, streams, events](#results-handles-streams-events)
- [CallbackHandler](#callbackhandler)
- [AgentClient](#agentclient)
- [Config and credentials](#config-and-credentials)

## AgentRuntime

`AgentRuntime(*, server_url=None, api_key=None, api_secret=None, config=None)`

Context manager (sync and async: `with` / `async with`).

| Method | Signature | Purpose |
|---|---|---|
| `run` | `(agent, prompt=None, *, version=None, media=None, session_id=None, idempotency_key=None, on_event=None, timeout=None, credentials=None, context=None, **kwargs) -> AgentResult` | Run synchronously |
| `run_async` | same as `run` | Async run |
| `start` | `(agent, prompt=None, *, version=None, media=None, session_id=None, idempotency_key=None, context=None, **kwargs) -> AgentHandle` | Fire-and-forget |
| `start_async` | same as `start` | Async start |
| `stream` | `(agent=None, prompt=None, *, version=None, handle=None, media=None, session_id=None, **kwargs) -> AgentStream` | Stream events |
| `stream_async` | same as `stream` | `-> AsyncAgentStream` |
| `deploy` | `(*agents, packages=None, schedules=_UNSET) -> list[DeploymentInfo]` | Compile + register |
| `deploy_async` | same | Async deploy |
| `serve` | `(*agents, packages=None, blocking=True) -> None` | Register + poll workers |
| `plan` | `(agent) -> dict` | Compile to workflow def |
| `resume` | `(execution_id, agent, *, timeout=None) -> AgentHandle` | Re-attach + re-register workers |
| `resume_async` | same | Async resume |
| `prepare` | `(agent) -> None` | Pre-register workers, no execution |
| `get_status` | `(execution_id) -> AgentStatus` | Execution status |
| `respond` | `(execution_id, output) -> None` | Complete a human task |
| `approve` / `reject` | `(execution_id)` / `(execution_id, reason="")` | HITL approve / reject |
| `send_message` | `(execution_id, message) -> None` | Push to workflow message queue |
| `pause` / `cancel` / `stop` | `(execution_id[, reason])` | Lifecycle control |
| `signal` | `(execution_id, message) -> None` | Inject persistent context |
| `shutdown` | `() -> None` | Stop all workers |
| `client` (property) | `-> AgentClient` | Control-plane client |
| `schedules_client` | `() -> ScheduleClient` | Shared schedule client |

Async variants exist for status/respond/approve/reject/send/stop/shutdown
(`*_async`). Module-level wrappers using a singleton runtime: `run`, `run_async`,
`start`, `start_async`, `stream`, `stream_async`, `resume`, `resume_async`, `deploy`,
`deploy_async`, `serve`, `plan`, `configure`, `shutdown`.

## Agent

`Agent(name, model="", instructions="", tools=None, agents=None,
strategy=Strategy.HANDOFF, router=None, output_type=None, guardrails=None,
memory=None, dependencies=None, max_turns=25, max_tokens=None, timeout_seconds=0,
temperature=None, reasoning_effort=None, stop_when=None, termination=None,
handoffs=None, allowed_transitions=None, introduction=None, metadata=None,
local_code_execution=False, allowed_languages=None, allowed_commands=None,
code_execution=None, cli_commands=False, cli_allowed_commands=None, cli_config=None,
enable_planning=False, callbacks=None, include_contents=None,
thinking_budget_tokens=None, required_tools=None, gate=None, base_url=None,
credentials=None, stateful=False, context_window_budget=None, prefill_tools=None,
fallback_max_turns=None, synthesize=True, masked_fields=None, planner=None,
fallback=None, planner_context=None)`

- `name` must match `[a-zA-Z_][a-zA-Z0-9_-]*`.
- `model` is `"provider/model"`; empty means inherit from parent or treat as an
  external workflow reference.
- `instructions` may be a string, a callable returning a string, or a `PromptTemplate`.
- `strategy` accepts a `Strategy` value or a string.
- Properties: `.is_claude_code`, `.external`. `a >> b` builds a sequential pipeline.

Classmethod: `Agent.from_instance(instance, name=None)` — resolve `@agent` methods on
an object into one `Agent` (by `name`) or `list[Agent]` (all). `@tool`/`@guardrail`
methods on the instance are auto-attached.

`@agent(func=None, *, name=None, model="", tools=None, guardrails=None, agents=None,
strategy=Strategy.HANDOFF, max_turns=25, max_tokens=None, temperature=None,
metadata=None, credentials=None, context_window_budget=None, ...)` — register a
function as an agent. The docstring is the instructions; returning a string gives
dynamic instructions.

`Strategy` enum: `HANDOFF`, `SEQUENTIAL`, `PARALLEL`, `ROUTER`, `ROUND_ROBIN`,
`RANDOM`, `SWARM`, `MANUAL`, `PLAN_EXECUTE`.

`PromptTemplate(name, variables={}, version=None)` — reference a server-side template.

`scatter_gather(name, worker, *, model=None, instructions="", tools=None,
retry_count=None, retry_delay_seconds=None, fail_fast=False, **kwargs) -> Agent`.

## Tools

`@tool(func=None, *, name=None, external=False, approval_required=False,
timeout_seconds=None, guardrails=None, credentials=None, stateful=False,
max_calls=None, retry_count=2, retry_delay_seconds=2,
retry_policy="linear_backoff")` — register a function as a tool. Type hints +
docstring produce the schema. Attaches `_tool_def`.

`ToolDef` fields: `name`, `description=""`, `input_schema={}`, `output_schema={}`,
`func`, `approval_required=False`, `timeout_seconds=None`, `tool_type="worker"`,
`config={}`, `guardrails=[]`, `credentials=[]`, `stateful=False`, `max_calls=None`,
`retry_count=2`, `retry_delay_seconds=2`, `retry_policy="linear_backoff"`. Method
`ToolDef.call(**kwargs) -> PrefillToolCall`.

`ToolContext` fields: `session_id`, `execution_id`, `agent_name`, `metadata`,
`dependencies`, `state`. Declare a `context: ToolContext` parameter to receive it.

`PrefillToolCall(tool_name, arguments, tool_def=None)` — a pre-declared tool call for
`Agent(prefill_tools=[...])`, created via `tool_def.call(...)`.

Helpers: `get_tool_def(obj) -> ToolDef`, `get_tool_defs(tools) -> list[ToolDef]`.
`ToolRegistry.register_tool_workers(tools, agent_name, domain=None,
agent_stateful=False)` (used internally by the runtime).

### Built-in tools

- `http_tool(name, description, url, method="GET", headers=None, input_schema=None, accept=["application/json"], content_type="application/json", credentials=None)`
- `api_tool(url, name=None, description=None, headers=None, tool_names=None, max_tools=64, credentials=None)`
- `mcp_tool(server_url, name=None, description=None, headers=None, tool_names=None, max_tools=64, credentials=None)`
- `human_tool(name, description, input_schema=None)`
- `image_tool(name, description, llm_provider, model, input_schema=None, **defaults)`
- `audio_tool(name, description, llm_provider, model, input_schema=None, **defaults)`
- `video_tool(name, description, llm_provider, model, input_schema=None, **defaults)`
- `pdf_tool(name="generate_pdf", description="...", input_schema=None, **defaults)`
- `index_tool(name, description, vector_db, index, embedding_model_provider, embedding_model, namespace="default_ns", chunk_size=None, chunk_overlap=None, dimensions=None, input_schema=None)`
- `search_tool(name, description, vector_db, index, embedding_model_provider, embedding_model, namespace="default_ns", max_results=5, dimensions=None, input_schema=None)`
- `wait_for_message_tool(name, description, batch_size=1, blocking=True)`
- `agent_tool(agent, name=None, description=None, retry_count=None, retry_delay_seconds=None, optional=None)`

OCG (from `conductor.ai.agents.ocg`):
`ocg_agent(*, model, url, name="ocg_agent", credential=None, instructions=None,
max_turns=10, query=True, entities=True, memory=True) -> Agent`;
`ocg_tools(*, url, credential=None, query=True, entities=True, memory=True) ->
list[ToolDef]`; `OCG_SYSTEM_PROMPT`.

## Guardrails

`@guardrail(func=None, *, name=None)` — register a `(str) -> GuardrailResult` function.

`Guardrail(func=None, position=Position.OUTPUT, on_fail=OnFail.RETRY, name=None,
max_retries=3)`. `func=None` + `name=` makes an external guardrail.

`RegexGuardrail(patterns, *, mode="block", position=Position.OUTPUT,
on_fail=OnFail.RETRY, name=None, message=None, max_retries=3)` — `mode="block"` fails
on match, `"allow"` fails on no match.

`LLMGuardrail(model, policy, *, position=Position.OUTPUT, on_fail=OnFail.RETRY,
name=None, max_retries=3, max_tokens=None)` — LLM judges content against `policy`
(requires `litellm` at evaluation time).

`GuardrailResult(passed, message="", fixed_output=None)`.
`OnFail`: `RETRY`, `RAISE`, `FIX`, `HUMAN`. `Position`: `INPUT`, `OUTPUT`.
`GuardrailDef(name, description, func)`.

## Termination

Composable with `&` (all) and `|` (any). All take a context dict and return a
`TerminationResult(should_terminate, reason="")`.

- `TextMentionTermination(text, *, case_sensitive=False)`
- `StopMessageTermination(stop_message="TERMINATE")`
- `MaxMessageTermination(max_messages)`
- `TokenUsageTermination(max_total_tokens=None, max_prompt_tokens=None, max_completion_tokens=None)`
- `TerminationCondition` (base)

## Handoffs

For `strategy="swarm"`, in `handoffs=[...]`. All carry `target`.

- `OnToolResult(target, tool_name="", result_contains=None)` — after a named tool runs (optionally only if the result contains a substring).
- `OnTextMention(target, text="")` — LLM output contains `text` (case-insensitive).
- `OnCondition(target, condition=...)` — `condition(context) -> bool`.
- `HandoffCondition` (base).

## TextGate

From `conductor.ai.agents.gate`: `TextGate(text, case_sensitive=True)` — stop a `>>`
pipeline after this agent when its output contains `text`. Compiled server-side.

## Schedules

`Schedule(name, cron, timezone="UTC", input={}, catchup=False, paused=False,
start_at=None, end_at=None, description=None)` — `cron` is a 5- or 6-field expression.

`ScheduleInfo` (read model) fields include `name`, `short_name`, `agent`, `cron`,
`timezone`, `input`, `paused`, `catchup`, `next_run`, `create_time`, `update_time`, ...

`ScheduleClient` (via `runtime.schedules_client()` or `runtime.client.schedules`):

| Method | Signature |
|---|---|
| `save` | `(schedule: Schedule, agent_name) -> None` |
| `get` | `(wire_name, agent_name=None) -> ScheduleInfo` |
| `list_for_agent` | `(agent_name) -> list[ScheduleInfo]` |
| `pause` / `resume` | `(wire_name[, reason])` / `(wire_name)` |
| `delete` | `(wire_name) -> None` |
| `run_now` | `(info: ScheduleInfo) -> str` (execution_id) |
| `preview_next` | `(cron, n=5, start_at=None, end_at=None) -> list[int]` |
| `reconcile` | `(agent_name, desired: list[Schedule] | None) -> None` |

Errors: `ScheduleError`, `ScheduleNameConflict`, `ScheduleNotFound`,
`InvalidCronExpression`.

## Results, handles, streams, events

### AgentResult

Fields: `output`, `execution_id`, `correlation_id`, `messages`, `tool_calls`,
`status` (`Status`), `token_usage` (`TokenUsage`), `metadata`, `finish_reason`
(`FinishReason`), `error`, `events`, `sub_results`. Properties: `is_success()`,
`is_failed()`, `is_rejected()`. Method: `print_result()`.

`Status`: `COMPLETED`, `FAILED`, `TERMINATED`, `TIMED_OUT`.
`FinishReason`: `STOP`, `LENGTH`, `TOOL_CALLS`, `ERROR`, `CANCELLED`, `TIMEOUT`,
`GUARDRAIL`, `REJECTED`, `STOPPED`.
`TokenUsage`: `prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens`.
`DeploymentInfo`: `registered_name`, `agent_name`.

### AgentHandle

Fields: `execution_id`, `correlation_id`, `run_id`, `is_resumed`.

| Method | Signature | Notes |
|---|---|---|
| `get_status` | `() -> AgentStatus` | |
| `stream` | `() -> AgentStream` | |
| `join` | `(timeout=None) -> AgentResult` | block until terminal |
| `respond` | `(output: dict, *, event=None) -> None` | answer a `human_tool` |
| `approve` | `(*, event=None) -> None` | approve pending tool |
| `reject` | `(reason="", *, event=None) -> None` | reject pending tool |
| `send` | `(message: str, *, event=None) -> None` | multi-turn message |
| `pause` / `resume` / `cancel` / `stop` | `()` / `()` / `(reason="")` / `()` | lifecycle |

The `event=` parameter targets a specific pending pause (event-targeted HITL). Every
method has an `*_async` counterpart (e.g. `approve_async`, `join_async`).

`AgentStatus` fields: `execution_id`, `is_complete`, `is_running`, `is_waiting`,
`output`, `status`, `reason`, `current_task`, `messages`, `pending_tool`.

### AgentStream / AsyncAgentStream

Iterable (sync `for` / async `for`) yielding `AgentEvent`. Fields: `handle`, `events`,
`result`, `execution_id`. Methods: `get_result()`, and HITL `respond`/`approve`/
`reject`/`send` (each with `*, event=None`). `AsyncAgentStream`'s methods are async.

### AgentEvent / EventType

`AgentEvent` fields: `type`, `content`, `tool_name`, `args`, `result`, `target`,
`output`, `execution_id`, `guardrail_name`.

`EventType`: `THINKING`, `TOOL_CALL`, `TOOL_RESULT`, `HANDOFF`, `WAITING`, `MESSAGE`,
`ERROR`, `DONE`, `GUARDRAIL_PASS`, `GUARDRAIL_FAIL`.

## CallbackHandler

Subclass and override any of: `on_agent_start`, `on_agent_end`, `on_model_start`,
`on_model_end`, `on_tool_start`, `on_tool_end`. Each is `(self, **kwargs) ->
Optional[dict]`: return `None` to continue, a non-empty dict to short-circuit and
override. Pass instances via `Agent(callbacks=[...])`; they chain in list order.

## AgentClient

The control-plane client (formerly `AgentHttpClient`, alias kept). Reach it via
`runtime.client`, or construct standalone:
`AgentClient(server_url="", api_key="", auth_key="", auth_secret="", *, runtime=None)`.

| Method | Signature | Purpose |
|---|---|---|
| `run` / `run_async` | `(agent, prompt=None, *, media=None, session_id=None, idempotency_key=None, timeout=None, context=None, static_plan=None) -> AgentResult` | Compile + start + poll (no local workers) |
| `start` / `start_async` | same args | `-> AgentHandle` |
| `deploy` / `deploy_async` | `(*agents) -> list[DeploymentInfo]` | Compile + register |
| `schedule` | `(agent, schedules) -> DeploymentInfo` | Deploy + reconcile cron schedules |
| `get_status` | `(execution_id) -> dict` | |
| `respond` | `(execution_id, body) -> None` | |
| `stop` | `(execution_id) -> None` | |
| `signal` | `(execution_id, message) -> None` | |
| `stream_sse` | `(execution_id) -> AsyncIterator[dict]` | |
| `schedules` (property) | `-> ScheduleClient` | |
| `close` | `() -> None` (async) | |

Lower-level endpoint methods (`start_agent`, `deploy_agent`, `compile_agent`) are also
available.

## Config and credentials

`AgentConfig` (dataclass) fields: `server_url="http://localhost:6767/api"`,
`api_key=None`, `auth_key=None`, `auth_secret=None`, `llm_retry_count=3`,
`worker_poll_interval_ms=100`, `worker_thread_count=1`, `auto_start_workers=True`,
`auto_start_server=True`, `daemon_workers=True`, `auto_register_integrations=False`,
`streaming_enabled=True`, `secret_strict_mode=False`, `log_level="INFO"`. Classmethod
`AgentConfig.from_env()` reads the `AGENTSPAN_*` variables (see [Getting
started](getting-started.md#environment-variables)). Property `api_secret` aliases
`auth_secret`.

`get_secret(name) -> str` — read a credential inside a `@tool(credentials=[...])`
function. `resolve_credentials(input_data, names) -> dict` — for external workers.
Errors: `CredentialNotFoundError`, `CredentialAuthError`, `CredentialRateLimitError`,
`CredentialServiceError`.

`ClaudeCode(model_name="", permission_mode=PermissionMode.ACCEPT_EDITS)` with
`PermissionMode` ∈ {`DEFAULT`, `ACCEPT_EDITS`, `PLAN`, `BYPASS`}; `to_model_string()`.

Skills: `skill(path, model="", agent_models=None, search_path=None, params=None) ->
Agent`; `load_skills(path, model="", agent_models=None) -> dict[str, Agent]`;
`SkillLoadError`.

Exceptions: `AgentspanError`, `AgentAPIError`, `AgentNotFoundError`,
`ConfigurationError`.
