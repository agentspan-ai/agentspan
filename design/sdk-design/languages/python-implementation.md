# Python SDK — Reference Implementation

**Status:** Refreshed 2026-06-26

**Scope:** This document describes how the Python SDK implements the cross-language SDK contract. Python is the *reference implementation*: it is the first SDK to land every feature, and the other language SDKs (TypeScript, C#, Java) are translated from its behavior. When this doc and another SDK disagree, Python is correct and the other SDK has drifted. The shared, language-neutral contract lives in [`../../sdk-design.md`](../../sdk-design.md); the platform-level compilation/execution model lives in [`../../agentspan-design.md`](../../agentspan-design.md). This file documents only the Python-observed internals and gotchas — it does not re-derive the model.

Cross-links: contract [`../../sdk-design.md`](../../sdk-design.md) · platform [`../../agentspan-design.md`](../../agentspan-design.md) · API [`../../api-design.md`](../../api-design.md) · frameworks [`../../framework-integration.md`](../../framework-integration.md) · tools/credentials [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md).

---

## 1. Overview

The Python SDK lets you define `Agent` objects in Python and run them as durable Conductor workflows. The SDK serializes an agent tree to JSON, the **server-side Java compiler** turns that into a Conductor `WorkflowDef`, and a long-lived worker process executes your tool functions as distributed Conductor tasks. Each agent compiles to one workflow; user-facing runs are called "executions".

Reference-implementation design principles (these hold across all SDKs):

1. **Everything is an Agent.** One primitive for single agents, multi-agent teams, and nested hierarchies — no separate Team/Network/Swarm classes.
2. **Server-first execution.** Tools execute as distributed Conductor tasks, not in-process. The agent survives process crashes; human approvals can take days.
3. **Compile, don't interpret.** Agent definitions compile to static workflow JSON. Behavior is inspectable, versioned, reproducible.
4. **Zero config for simple cases.** `Agent + tool + run` works in ~5 lines; advanced features (memory, guardrails, streaming) layer on without changing the core API.
5. **Conductor-native.** Every SDK concept maps directly to a Conductor primitive.

**Naming & distribution:**

| Aspect | Value |
|---|---|
| PyPI package | `conductor-agent-sdk` |
| Import namespace | `conductor.ai.agents` (public surface), with internals under `conductor.ai.agents.runtime`, `conductor.ai.models` |
| Supported Python | 3.10–3.13 (`requires-python = ">=3.10,<3.14"`) |
| Logger root | `conductor.ai.agents.*` |
| CLI binary | `agentspan` (console script → `conductor.ai.cli:main`) |
| Env vars | `AGENTSPAN_*` |
| OTel tracer name | `conductor.ai.agents` |

> Runtime contracts that are intentionally still `agentspan` (these are wire/operator-facing and must match the server): the `AGENTSPAN_*` environment variables, the `agentspan` CLI binary name, and the `__agentspan_ctx__` task-input context key. Logger names and the import namespace follow `conductor.ai`.

---

## 2. Package & source layout

Source root: `sdk/python/src/conductor/ai/`

```
conductor/ai/
├── __init__.py
├── __main__.py                  # mirrors the `agentspan` console script
├── agents/                      # the SDK proper — public API in __init__.py
│   ├── agent.py                 # Agent, AgentDef, Strategy, @agent, scatter_gather
│   ├── run.py                   # module-level run/start/stream/deploy/resume/serve + singleton
│   ├── result.py                # AgentResult, AgentStatus, AgentEvent, EventType, AgentHandle, streams
│   ├── config_serializer.py     # Agent tree -> AgentConfig JSON (the wire DTO)
│   ├── guardrail.py             # @guardrail, Guardrail, OnFail, Position, GuardrailResult
│   ├── handoff.py / termination.py / memory.py / semantic_memory.py / plans.py
│   ├── tool.py                  # @tool, http_tool, mcp_tool, @worker_task, ToolContext
│   ├── skill.py / claude_code.py / cli_config.py / code_execution_config.py / code_executor.py
│   ├── openai_compat.py / langchain.py / ocg.py / gate.py / callback.py / tracing.py / exceptions.py
│   ├── _internal/               # model_parser, provider_registry, schema_utils, token_utils
│   ├── frameworks/              # langchain, langgraph, claude_agent_sdk adapters + serializer
│   ├── runtime/                 # the execution engine (see §4)
│   │   ├── runtime.py           # AgentRuntime — compile/prepare/execute/extract/stream
│   │   ├── _dispatch.py         # dispatch worker internals (see §5)
│   │   ├── worker_manager.py    # long-lived worker process lifecycle
│   │   ├── tool_registry.py     # worker registration + global registries
│   │   ├── config.py            # AgentConfig.from_env() — AGENTSPAN_* loader
│   │   ├── http_client.py       # AgentClient (REST + SSE)
│   │   ├── server.py            # locate/install the `agentspan` CLI binary
│   │   ├── _liveness.py / discovery.py / mcp_discovery.py / secret_injection.py
│   │   └── credentials/         # accessor (get_secret), fetcher, types
│   ├── schedule/                # recurring-execution API/client
│   └── testing/                 # pytest plugin, assertions, mocks, eval runner, recording
├── cli/                         # deploy.py + discover.py — invoked BY the native CLI binary
└── models/                      # multi-model LLM management (providers, routing, monitoring)
```

The public API is re-exported from `conductor.ai.agents.__init__`; users import from there (e.g. `from conductor.ai.agents import Agent, tool, run`).

---

## 3. Compilation pipeline

Compilation is **always server-side**. The SDK never builds workflow JSON locally; it serializes the agent and POSTs it to the Java compiler. For the full compilation/execution model — strategy dispatch, the compiled workflow shapes, durability semantics — see [`../../agentspan-design.md`](../../agentspan-design.md). What follows is only the Python-observed surface.

```
User Code          Python SDK                         Java Server
==========         ==========                         ===========
Agent(             AgentConfigSerializer.serialize()
  name, model,         |  -> AgentConfig JSON dict
  tools, agents,       v
  ...           POST {server_url}/agent/compile   ->  AgentCompiler.compile()
)                  {"agentConfig": {...}}              dispatches by shape:
                       |                                 agents & !tools -> MultiAgentCompiler
                   ServerCompiledWorkflow  <--JSON--   agents & tools   -> compileHybrid
                   (wraps WorkflowDef)     workflowDef  tools           -> compileWithTools
                       |                                 no tools        -> compileSimple
                   tool_registry.register_tool_workers()
                       v
                   @worker_task functions registered, worker process started
```

- Serializer: `config_serializer.py` → `AgentConfigSerializer.serialize(agent)` returns a dict matching the Java `AgentConfig` DTO. Callables (tools, guardrails, `stop_when`, router, handoffs) are registered as workers locally and sent as **task-name references**, never code.
- Compile call: `AgentRuntime._compile_via_server()` POSTs `{"agentConfig": config_json}` to `{server_url}/agent/compile` (30s timeout), reads `workflowDef` from the response, and wraps it in `ServerCompiledWorkflow`. There is an async twin `_compile_via_server_async()` using `AgentClient`. Results are cached per `agent.name`.
- "Local vs server compile" survives only as *terminology in streaming detection and guardrail registration* (the SDK registers both an individual-worker form and a combined-worker form so either compile path on the server resolves the task names). The compile itself is server-only.

**Python-observed compiled shapes** (illustrative; canonical definitions in the platform doc):

*Single agent with tools — DoWhile loop:*
```
[SetVariable: init messages]
   -> [DoWhile]
        [LlmChatComplete]  reads ${workflow.variables.messages}, json_output=True
        [dispatch_worker]  routes tool calls, updates messages
        [SetVariable]      messages = ${dispatch.output.messages}
        [stop_when_worker] (optional, if agent.stop_when set)
      condition: $.loop.iteration < max_turns
                 && $.dispatch.continue_loop == true
                 [&& $.stop_when.should_continue == true]
   -> Output: ${dispatch.output.result}
```
Key detail: in DoWhile conditions, task refs map to outputData with **no `.output` wrapper** — `$.dispatch.continue_loop`, not `$.dispatch.output.continue_loop`.

*Single agent, no tools:* one `[LlmChatComplete]` over `[system_prompt, user_prompt]` → `${llm.output.result}`.

Multi-agent strategies (handoff/router → `SwitchTask` + inline sub-workflows; sequential → chained `SubWorkflow`; parallel → `Fork`/`Join`; hybrid → DoWhile with `transfer_to_{name}` tools feeding a `SwitchTask`) follow the platform doc — the SDK only chooses the strategy via the serialized config; the server emits the structure.

---

## 4. Runtime lifecycle

`run()`, `start()`, `stream()`, `run_async()`, `deploy()`, `resume()`, `serve()` (in `run.py`) share a module-level singleton `AgentRuntime`, created lazily on first use and torn down via `atexit`:

```python
# run.py
_default_runtime = None  # created on first use, thread-safe
atexit.register(_shutdown_default_runtime)

def run(agent, prompt, *, runtime=None, **kwargs):
    rt = runtime or _get_default_runtime()
    return rt.run(agent, prompt, **kwargs)
```

This avoids spinning up new Conductor clients and worker processes per call. Workers start once and run until process exit (not stopped after each call).

`AgentRuntime.run()` flow:

```
run(agent, prompt)
  -> input guardrails  (checked here, before execution; on_fail="raise" -> ValueError)
  -> _compile_agent(agent)          # cached per agent.name -> ServerCompiledWorkflow
  -> _prepare(agent)
        _register_workers(agent)    # tool_registry.register_tool_workers()
        WorkerManager.start()       # long-lived; restarts if new tools registered
  -> execute workflow_input={prompt, session_id, __agentspan_ctx__}
  -> _extract_output(workflow_run, agent)
        parse structured output (Pydantic/dataclass) if output_type set
        extract handoff result from nested dict
  -> AgentResult
```

`WorkerManager` is the single long-lived worker host (poll interval from `AGENTSPAN_WORKER_POLL_INTERVAL`, threads from `AGENTSPAN_WORKER_THREADS`). Configuration is loaded by `AgentConfig.from_env()` (`runtime/config.py`):

```
AGENTSPAN_* env vars  ->  AgentConfig (dataclass via from_env())  ->  AgentRuntime
```

| Field | Env var | Default |
|---|---|---|
| server_url | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` |
| api_key | `AGENTSPAN_API_KEY` | — |
| auth_key / auth_secret | `AGENTSPAN_AUTH_KEY` / `AGENTSPAN_AUTH_SECRET` | — |
| log_level | `AGENTSPAN_LOG_LEVEL` | `INFO` |
| llm_retry_count | `AGENTSPAN_LLM_RETRY_COUNT` | 3 |
| worker_poll_interval_ms | `AGENTSPAN_WORKER_POLL_INTERVAL` | 100 |
| worker_thread_count | `AGENTSPAN_WORKER_THREADS` | 1 |
| auto_start_workers | `AGENTSPAN_AUTO_START_WORKERS` | True |
| auto_start_server | `AGENTSPAN_AUTO_START_SERVER` | True |
| daemon_workers | `AGENTSPAN_DAEMON_WORKERS` | True |
| auto_register_integrations | `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | False |
| streaming_enabled | `AGENTSPAN_STREAMING_ENABLED` | True |
| secret_strict_mode | `AGENTSPAN_SECRET_STRICT_MODE` | False |
| liveness check | `AGENTSPAN_LIVENESS_ENABLED` | (on) |

The config is also serialized into the agent config JSON (timeout, retry count, etc.) so the server compiles matching task definitions.

---

## 5. Dispatch worker internals

`runtime/_dispatch.py` hosts the universal tool-execution router (`dispatch_worker`) — a single Conductor worker task shared by all agents that processes each LLM response.

```
LLM response
  -> parse (fuzzy: strip markdown fences, extract JSON, normalize keys)
  -> is it a tool call (type == "function")?
       no  -> final answer: continue_loop=False, result=text
       yes -> circuit breaker (3 consecutive failures for this tool?)
                tripped -> error message, continue_loop=True
                ok      -> approval_required?
                            yes -> needs_approval=True, continue_loop=False (HITL pause)
                            no  -> execute tool function
                                     inject ToolContext if declared
                                     coerce args to annotations; validate result JSON-serializable
                                     append result to messages; continue_loop=True
```

**Critical Python-specific gotchas** (these are *load-bearing* — other SDKs must replicate the equivalent):

- **`object` type annotations.** `llm_response` and `messages` parameters are typed `object`, not `dict`/`list`. Conductor's worker framework calls `convert_from_dict_or_list()` on non-simple types, and bare `list`/`dict` crash with `IndexError` inside `typing.get_args()`. `object` short-circuits that.
- **No `from __future__ import annotations`.** `_dispatch.py` deliberately omits it (see the module docstring) because the worker framework needs **real type objects**, not stringized annotations, for runtime parameter resolution. (By contrast `config_serializer.py` *does* use it — it never feeds the worker framework.)
- **Module-level global registries.** Tool functions, per-tool error counts, and approval flags live in module-level dicts in `tool_registry.py` (`_tool_registry`, `_tool_error_counts`, `_tool_approval_flags`). The dispatch worker is registered once per task name and shared across all agents, so per-agent state cannot live on the function — it must be keyed in globals.
- **Framework callables.** Tools marked `_agentspan_framework_callable` (LangChain/LangGraph/OpenAI/Claude adapters) get kwargs/results normalized (`SimpleNamespace` for `ctx`/`context`/`agent`; recursive dataclass/`model_dump`/`__dict__` flattening) before/after invocation.
- **Result serialization guard.** `_validate_serializable()` rejects non-JSON tool returns with `ToolSerializationError` and an actionable message.

---

## 6. Streaming

`stream()` / `stream_async()` poll the workflow with `include_tasks=True`, track seen task IDs, and emit typed `AgentEvent`s for new/changed tasks. (The SDK also supports SSE via `AgentClient`, falling back to polling when SSE is unavailable.)

`EventType` (from `result.py`): `thinking`, `tool_call`, `tool_result`, `handoff`, `waiting`, `message`, `error`, `done`, `guardrail_pass`, `guardrail_fail`.

| Task observed | Condition | Event(s) |
|---|---|---|
| `LLM_CHAT_COMPLETE` | new task | `THINKING` |
| dispatch task (local-compile form) | COMPLETED, `function` in output | `TOOL_CALL` + `TOOL_RESULT` |
| `call_*` tool task (server-compile form) | COMPLETED, non-system task type | `TOOL_CALL` + `TOOL_RESULT` (args stripped of `__agentspan_ctx__`) |
| guardrail task | COMPLETED, `passed` present | `GUARDRAIL_PASS` / `GUARDRAIL_FAIL` |
| `SUB_WORKFLOW` | new task | `HANDOFF` |
| workflow | PAUSED | `WAITING` (carries HITL resume target) |
| workflow | FAILED | `ERROR` |
| workflow | COMPLETED | `DONE` |

Poll cadence: 0.5s normally; backs off to 2s while waiting on a human (HITL) task.

---

## 7. Guardrails & credentials (SDK-side)

**Guardrails** run in two places:

1. **Input guardrails** — checked in `AgentRuntime.run()` *before* workflow execution. `on_fail="raise"` raises `ValueError`. This is a runtime check, not compiled.
2. **Output guardrails** — compiled into the DoWhile loop as durable tasks. Each custom guardrail is registered both as an individual worker (server-compile path, keyed by `guardrail.name`) and bundled into a combined worker (local-compile path). After each guardrail task a `SwitchTask` routes on the result: retry (append feedback + continue), raise (terminate), fix (use corrected output), or human (HumanTask escalation).

API surface (`guardrail.py`): the `@guardrail` decorator, `OnFail`/`Position` enums (both `str` subclasses, so plain `"retry"`/`"output"` stay backward-compatible), and `Guardrail`/`GuardrailDef`:

```python
from conductor.ai.agents import guardrail, Guardrail, GuardrailResult, OnFail, Position

@guardrail
def no_pii(content: str) -> GuardrailResult: ...

agent = Agent(guardrails=[Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY)])
# External guardrail — worker runs in another service, referenced by name only:
agent = Agent(guardrails=[Guardrail(name="compliance_checker", on_fail=OnFail.RETRY)])
```

**Credentials** (`runtime/credentials/`): tool workers call `get_secret(name)` (accessor) which uses `WorkerCredentialFetcher` to fetch secrets from the server, authorized by the `__agentspan_ctx__.execution_token` extracted from the Conductor task input. Errors are typed: `CredentialNotFoundError`, `CredentialAuthError`, `CredentialRateLimitError`, `CredentialServiceError`. See [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md) for the full model.

---

## 8. Language-specific design choices / gotchas

- **No Pydantic dependency in the SDK core.** Models and config use `dataclasses`; Pydantic is touched only when an external framework (e.g. OpenAI structured output) requires it. `output_type` parsing in `_extract_output` handles Pydantic *or* dataclass.
- **`uv`, not `pip`,** for all package management (see `sdk/python/CLAUDE.md`).
- **CLI is a native binary, not Python.** The `agentspan` console script (`cli/__init__.py:main`) locates/downloads a platform-specific native binary (`server.py` / `_ensure_binary()`, honoring `AGENTSPAN_FORCE_DOWNLOAD`) and execs it. The Python modules under `cli/` (`deploy.py`, `discover.py`) are *invoked by* that native CLI — `discover.py` scans `.py` files for module-level `Agent` instances; `deploy.py` deploys them.
- **`from __future__ import annotations` is conditional**, file by file — required to be *absent* in `_dispatch.py` (worker type resolution), fine elsewhere.
- **Tracer name is `conductor.ai.agents`** (OTel), distinct from the `agentspan` wire/operator surface — tracing only activates if `opentelemetry-api` is installed.
- **OpenAI/Claude/LangChain/LangGraph compatibility** is provided via adapters (`openai_compat.py`, `frameworks/*`) that convert foreign agent/tool objects into Agentspan agents; the runtime marks the resulting callables `_agentspan_framework_callable` so the dispatch worker normalizes their I/O. See [`../../framework-integration.md`](../../framework-integration.md).

---

## 9. Testing

Layout under `sdk/python/tests/` (`testpaths = ["tests"]`, 120s per-test timeout):

| Location | Scope |
|---|---|
| `tests/unit/` | **1701 unit tests** — no server required (agent, tool, compiler, dispatch, runtime, guardrail, memory, result, schedule, skill, framework adapters, examples, etc.) |
| `tests/integration/` | ~130 tests against a live Conductor server |
| `tests/cli/` | ~8 CLI-binary tests |
| `tests/` (root) | `test_kitchen_sink.py` and harnesses (`_worker_harness.py`, `count_workers.py`) |
| `tests/fixtures/`, `tests/compilation_diffs/` | shared fixtures (skills) and compiled-workflow golden diffs |

Representative unit files: `test_agent.py`, `test_tool.py`/`test_dispatch.py`/`test_dispatch_advanced.py`, `test_compiler.py`/`test_config_serializer.py`/`test_runtime_server_compile.py`, `test_runtime.py`/`test_run.py`, `test_guardrail.py`, `test_memory.py`/`test_result.py`, `test_mcp_discovery.py`, `test_schedule.py`, `test_skill.py`, the `test_langchain_*`/`test_langgraph_*`/`test_claude_agent_sdk_worker.py` framework suites, and `test_example_*` for shipped examples.

A pytest plugin (`conductor.ai.agents.testing.pytest_plugin`, entry point `agentspan-testing`) plus `testing/` helpers (assertions, mocks, eval runner, recording, semantic/LLM-judge) support agent-level testing. Custom markers: `integration`, `e2e`, `sse`, `agent_correctness`, `semantic`.

**CI/CD** (`.github/workflows/ci.yml`): unit tests on Python 3.10–3.13, lint with `ruff`, type-check with `mypy`.
