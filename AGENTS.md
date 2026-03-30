# AGENTS.md — Guide for AI Agents Working on This Codebase

This file provides context for AI coding agents (Claude Code, Copilot, Cursor, etc.) working on the Conductor Agentic SDK.

## Project Overview

The `conductor-agentic` Python SDK compiles Python `Agent` definitions into durable [Conductor](https://github.com/conductor-oss/conductor) executions. Agents survive process crashes, tools scale as distributed workers, and human-in-the-loop approvals can pause for days.

**Package name:** `conductor-agentic`
**Import path:** `from conductor.agentic import ...`
**Python:** 3.9+
**License:** Apache 2.0

## Architecture

### Core Design Principles

1. **Everything is an Agent.** One class for single agents, multi-agent teams, and nested hierarchies. No Team, Network, or Swarm classes.
2. **Server-first execution.** Tools execute as distributed Conductor tasks. The agent survives process crashes.
3. **Compile, don't interpret.** Agent definitions are compiled into static Conductor workflow JSON at registration time.
4. **Zero config for simple cases.** `Agent + tool + run` works in 5 lines.
5. **Conductor-native.** Every SDK concept maps directly to a Conductor primitive.

### Compilation Pipeline

```
Agent(Python) → AgentCompiler.compile() → ConductorWorkflow(JSON) → execute on server
```

When `run(agent, prompt)` is called:
1. Agent is compiled into a Conductor workflow definition
2. Worker processes are started for `@tool` functions
3. Workflow is executed on the Conductor server
4. Result is extracted and returned as `AgentResult`

### Key Source Files

| File | Purpose |
|---|---|
| `src/conductor/agentic/agent.py` | `Agent` class — the single orchestration primitive |
| `src/conductor/agentic/tool.py` | `@tool` decorator, `ToolDef`, `http_tool()`, `mcp_tool()` |
| `src/conductor/agentic/run.py` | Top-level `run()`, `start()`, `stream()`, `run_async()`, `plan()` with singleton runtime |
| `src/conductor/agentic/result.py` | `AgentResult`, `AgentHandle`, `AgentStatus`, `AgentEvent`, `EventType` |
| `src/conductor/agentic/guardrail.py` | `Guardrail`, `GuardrailResult`, `RegexGuardrail`, `LLMGuardrail` |
| `src/conductor/agentic/memory.py` | `ConversationMemory` — session message history |
| `src/conductor/agentic/semantic_memory.py` | `SemanticMemory`, `MemoryStore`, `MemoryEntry` — long-term memory |
| `src/conductor/agentic/termination.py` | `TerminationCondition` and composable subclasses (`&`, `|` operators) |
| `src/conductor/agentic/handoff.py` | `HandoffCondition`, `OnToolResult`, `OnTextMention`, `OnCondition` |
| `src/conductor/agentic/code_executor.py` | `CodeExecutor` — Local, Docker, Jupyter, Serverless |
| `src/conductor/agentic/ext.py` | `UserProxyAgent`, `GPTAssistantAgent` |
| `src/conductor/agentic/tracing.py` | Optional OpenTelemetry integration |
| `src/conductor/agentic/__init__.py` | Public API surface — all exports |
| `src/conductor/agentic/compiler/agent_compiler.py` | Single agent compilation (DoWhile loops, tool dispatch) |
| `src/conductor/agentic/compiler/multi_agent_compiler.py` | Multi-agent strategies (handoff, sequential, parallel, router) |
| `src/conductor/agentic/compiler/tool_compiler.py` | `@tool` → TaskDef + ToolSpec + dispatch registration |
| `src/conductor/agentic/compiler/_dispatch.py` | Universal dispatch worker (fuzzy parsing, circuit breaker) |
| `src/conductor/agentic/runtime/runtime.py` | `AgentRuntime` — compile + execute + stream |
| `src/conductor/agentic/runtime/worker_manager.py` | Auto-register `@tool` as Conductor workers |
| `src/conductor/agentic/runtime/config.py` | `AgentConfig` — environment variable configuration |
| `src/conductor/agentic/_internal/model_parser.py` | Parse `"provider/model"` strings |
| `src/conductor/agentic/_internal/schema_utils.py` | JSON Schema generation from type hints |

### Conductor Primitive Mapping

| SDK Concept | Conductor Primitive |
|---|---|
| `Agent` | `ConductorWorkflow` |
| `@tool` function | Task definition + `@worker_task` |
| `http_tool` | `HttpTask` (server-side) |
| `mcp_tool` | `ListMcpTools` + `CallMcpTool` |
| Agentic loop | `DoWhileTask` |
| LLM call | `LlmChatComplete` (system task) |
| Handoff | `InlineSubWorkflowTask` |
| Sequential | Chain of `SubWorkflowTask` |
| Parallel | `ForkTask` + `JoinTask` |
| Human approval | `WaitTask` |
| Conversation state | `workflow.variables` |

## Coding Conventions

### Style

- **Linter:** ruff (`target-version = "py39"`, `line-length = 100`)
- **Type checker:** mypy (`python_version = "3.9"`, `ignore_missing_imports = true`)
- **Imports:** isort via ruff (`"I"` rule)
- **Python target:** 3.9+ (use `from __future__ import annotations` for newer typing syntax)

### Module-Level Patterns

- Every module uses `logging.getLogger("conductor.agentic.xxx")` for structured logging
- The dispatch worker (`_dispatch.py`) deliberately does NOT use `from __future__ import annotations` because Conductor's worker framework needs real type objects for parameter resolution
- The dispatch worker uses `object` type annotations (not `dict`/`list`) to avoid Conductor's `convert_from_dict_or_list()` issues
- Tool functions, error counts, and approval flags are stored in module-level registries (`_tool_registry`, `_tool_error_counts`, `_tool_approval_flags`)

### Public API

All public exports are listed in `src/conductor/agentic/__init__.py` and its `__all__` list. When adding a new public class or function, add it to both the imports and `__all__`.

### Agent Strategies

Valid strategies are defined in `agent.py`:
```
"handoff", "sequential", "parallel", "router", "round_robin", "random", "swarm", "manual"
```

### Guardrail `on_fail` Modes

```
"retry", "raise", "fix", "human"
```

`"human"` is only valid for `position="output"` (input guardrails are client-side).

## Testing

### Running Tests

```bash
# Unit tests (no server required)
python3 -m pytest tests/unit/ -v

# Integration tests (require running Conductor server)
python3 -m pytest tests/integration/ -v

# Lint
ruff check src/

# Type check
mypy src/conductor/agentic/ --ignore-missing-imports --no-strict-optional
```

### Test Files

| File | Scope |
|---|---|
| `tests/unit/test_agent.py` | Agent creation, validation, chaining, repr |
| `tests/unit/test_tool.py` | `@tool`, `http_tool`, `mcp_tool`, `get_tool_def`, `@worker_task` |
| `tests/unit/test_compiler.py` | Model parser, schema gen, tool compiler, DoWhile structure |
| `tests/unit/test_dispatch_advanced.py` | Fuzzy parsing, circuit breaker, approval, trimming, ToolContext |
| `tests/unit/test_multi_agent_compiler.py` | Handoff, sequential, parallel, router, hybrid |
| `tests/unit/test_result.py` | AgentResult, AgentStatus, AgentEvent, EventType |
| `tests/unit/test_termination.py` | Termination conditions and composable operators |
| `tests/integration/test_basic_execution.py` | End-to-end single agent execution |
| `tests/integration/test_multi_agent.py` | End-to-end multi-agent execution |

### Writing Tests

- Unit tests must run without a Conductor server (mock all external calls)
- Place unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Follow existing naming: `test_{module}.py`
- Use `pytest` fixtures and parametrize where appropriate
- do NOT use mocks.  Mocks considered harmful.  Write tests that uses the actual server
- SDK e2e tests MUST rely on the server to ensure we are testing the actual communication

### Examples
- Every feature MUST have an example in all the supported sdks (python/ etc)
- If the feature requires multiple examples, then write multiple examples to demonstrate how to use that feature
- Examples MUST be very clear and to the point.  Do not overload them with many features - one feature one examples.  Ofcourse you can use other features as required, but that is not a substitute for not writing examples for those features.

## Validation Checklist

Before merging any change:

1. **Unit tests pass:** `python3 -m pytest tests/unit/ -v`
2. **Lint clean:** `ruff check src/`
3. **Type check clean:** `mypy src/conductor/agentic/ --ignore-missing-imports --no-strict-optional`
4. **Public API unchanged** (or intentionally extended): check `__init__.py` `__all__`
5. **Examples still work** for affected features (run against a live Conductor server)

## Common Patterns

### Adding a New Tool Type

1. Add a constructor function in `tool.py` (like `http_tool()`, `mcp_tool()`)
2. Return a `ToolDef` with the appropriate `tool_type`
3. Handle the new type in `compiler/tool_compiler.py`
4. Export from `__init__.py`
5. Add a test in `tests/unit/test_tool.py`
6. Add an example in `examples/`

### Adding a New Multi-Agent Strategy

1. Add the strategy name to `_VALID_STRATEGIES` in `agent.py`
2. Implement the compilation in `compiler/multi_agent_compiler.py`
3. Add a test in `tests/unit/test_multi_agent_compiler.py`
4. Add an example in `examples/`

### Adding a New Guardrail Type

1. Subclass `Guardrail` in `guardrail.py` (see `RegexGuardrail`, `LLMGuardrail`)
2. Export from `__init__.py`
3. Add an example in `examples/`

### Adding a New Termination Condition

1. Subclass `TerminationCondition` in `termination.py`
2. Implement `should_terminate(self, context) -> TerminationResult`
3. Export from `__init__.py`
4. Add a test in `tests/unit/test_termination.py`

## Runtime Server (Java)

The `server/` directory contains the Agent Runtime — a Spring Boot server that embeds Conductor.

### Server Key Source Files

| File | Purpose |
|---|---|
| `server/src/.../controller/AgentController.java` | REST endpoints for agent lifecycle |
| `server/src/.../service/AgentService.java` | Core service: compile, start, list, search, get, delete agents |
| `server/src/.../compiler/AgentCompiler.java` | Compiles AgentConfig into Conductor WorkflowDef |
| `server/src/.../model/*.java` | DTOs: AgentConfig, AgentSummary, AgentExecutionSummary, AgentExecutionDetail, etc. |

### Server API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/agent/start` | POST | Compile, register, and start an agent execution |
| `/api/agent/compile` | POST | Compile agent config (inspect only) |
| `/api/agent/list` | GET | List all registered agents (filtered by `agent_sdk` metadata) |
| `/api/agent/executions` | GET | Search agent executions (with `start`, `size`, `sort`, `freeText`, `status`, `agentName` params) |
| `/api/agent/executions/{id}` | GET | Get detailed execution status (agent name, version, status, input, output, current task) |
| `/api/agent/get/{name}` | GET | Get agent definition (`?version=` optional) |
| `/api/agent/delete/{name}` | DELETE | Delete agent definition (`?version=` optional) |
| `/api/agent/stream/{id}` | GET | SSE event stream for a running execution |
| `/api/agent/{id}/respond` | POST | Respond to HITL task |
| `/api/agent/{id}/status` | GET | Get execution status (legacy) |

### Server Testing Requirements

**All runtime features MUST have real E2E integration tests.** Do not rely solely on mocked unit tests for HTTP endpoints or SSE streaming. E2E tests boot the full Spring context (`@SpringBootTest` with `RANDOM_PORT`) and test over real HTTP connections.

```bash
# Run server tests
cd server && ./gradlew test

# Build server
cd server && ./gradlew build
```

## CLI (Go)

The `cli/` directory contains the AgentSpan CLI — a Go binary built with Cobra that manages the server and agents.

### CLI Key Source Files

| File | Purpose |
|---|---|
| `cli/main.go` | Entry point |
| `cli/cmd/root.go` | Root command, version vars, `--server` flag |
| `cli/cmd/server.go` | `server start/stop/logs` — JAR download, PID management |
| `cli/cmd/server_unix.go` | Unix-specific process management (SIGTERM, Setpgid) |
| `cli/cmd/server_windows.go` | Windows-specific process management |
| `cli/cmd/run.go` | `agent run` — start agent by `--name` or `--config` |
| `cli/cmd/list.go` | `agent list` — table display of registered agents |
| `cli/cmd/get.go` | `agent get` — fetch agent definition as JSON |
| `cli/cmd/delete.go` | `agent delete` — remove agent definition |
| `cli/cmd/execution.go` | `agent execution` — search history with time parsing |
| `cli/cmd/status.go` | `agent status` — detailed execution status |
| `cli/cmd/update.go` | `update` — CLI self-update from GitHub releases |
| `cli/cmd/agent.go` | Agent parent command, SSE event formatting helpers |
| `cli/cmd/compile.go` | `agent compile` — compile config to agent def |
| `cli/cmd/init.go` | `agent init` — generate starter config file |
| `cli/cmd/stream.go` | `agent stream` — stream SSE events from running agent |
| `cli/cmd/respond.go` | `agent respond` — HITL approval/denial |
| `cli/cmd/configure.go` | `configure` — set server URL and auth |
| `cli/cmd/helpers.go` | Config/client factory helpers |
| `cli/client/client.go` | HTTP client for all server API calls |
| `cli/config/config.go` | Config loading (file + env vars), `~/.agentspan/` dir |

### CLI Build and Test

```bash
# Build locally
cd cli && go build -o agentspan .

# Verify
./agentspan version
./agentspan --help
./agentspan agent --help
./agentspan server --help

# Cross-platform build (all 6 targets)
cd cli && VERSION=0.1.0 ./build.sh
```

### CLI Coding Conventions

- **Language:** Go 1.25+
- **CLI framework:** Cobra (`github.com/spf13/cobra`)
- **Module path:** `github.com/agentspan/agentspan/cli`
- **Binary name:** `agentspan`
- **Config directory:** `~/.agentspan/`
- **No third-party HTTP clients** — use stdlib `net/http`
- **Platform-specific code** goes in `_unix.go` / `_windows.go` files with build tags
- **Build-time version** is injected via `-ldflags` (see `build.sh`)

### CLI Testing Checklist

When modifying CLI commands:

1. **Build succeeds:** `cd cli && go build -o /dev/null .`
2. **Cross-platform build succeeds:** `cd cli && VERSION=test ./build.sh` (all 6 targets)
3. **Help text is correct:** `./agentspan <command> --help`
4. **Manual smoke test** against a running server:
   - `agentspan server start` (downloads JAR, starts server)
   - `agentspan server logs -f` (follows log output)
   - `agentspan agent list` (returns `[]` or agent list)
   - `agentspan agent init testbot && agentspan agent run --config testbot.yaml "hello"`
   - `agentspan server stop` (sends SIGTERM, cleans PID file)

### CLI Distribution

Published via three channels (triggered by `cli-v*` git tags):

1. **GitHub Releases** — 6 platform binaries (`agentspan_{os}_{arch}`)
2. **npm** (`@agentspan/agentspan`) — JS wrapper downloads Go binary on `postinstall`
3. **Homebrew** (`agentspan/homebrew-agentspan` tap) — macOS/Linux formula

Release workflow: `.github/workflows/release-cli.yml`

### Adding a New CLI Command

1. Create `cli/cmd/<command>.go`
2. Define a `*cobra.Command` with `Use`, `Short`, `Args`, `RunE`
3. Register under the appropriate parent in `init()` (`agentCmd` for agent subcommands, `rootCmd` for top-level)
4. If the command calls a new API endpoint, add the client method in `cli/client/client.go`
5. If the endpoint doesn't exist, add it to `AgentService.java` + `AgentController.java`
6. Test: build, help text, manual smoke test

## Python SDK SSE Testing

SSE streaming tests are organized in three tiers:

1. **Tier 1 — SSE parsing unit tests** (`tests/unit/test_sse_parsing.py`): Tests `_parse_sse()` and `_sse_to_agent_event()` as pure functions. Zero dependencies, runs in CI.
2. **Tier 2 — Mock SSE server tests** (`tests/unit/test_sse_client.py`): Spins up a real HTTP server in a thread, tests the full `_stream_sse()` code path. No Java server or LLM needed.
3. **Tier 3 — Real server SSE tests** (`tests/integration/test_e2e_sse.py`): Full Python SDK → Runtime → SSE path. Requires `AGENTSPAN_STREAMING_ENABLED=true`.

```bash
# Tier 1 + 2 (no server needed, always run in CI)
cd python && python3 -m pytest tests/unit/test_sse_parsing.py tests/unit/test_sse_client.py -v

# Tier 3 (requires running runtime server + LLM key)
cd python && AGENTSPAN_STREAMING_ENABLED=true python3 -m pytest tests/integration/test_e2e_sse.py -v
```

**When adding SSE features:** Add tests at all three tiers. Tier 1+2 are mandatory for CI. Tier 3 validates the real cross-process path.

## CI/CD

GitHub Actions workflow at `.github/workflows/ci.yml`:
- Unit tests on Python 3.9-3.13
- Lint with ruff
- Type check with mypy

## Configuration

Environment variables:

| Variable | Description | Default |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | AgentSpan server API URL | `http://localhost:6767/api` |
| `AGENTSPAN_AUTH_KEY` | Auth key (Orkes Cloud) | None |
| `AGENTSPAN_AUTH_SECRET` | Auth secret (Orkes Cloud) | None |
| `AGENTSPAN_AGENT_TIMEOUT` | Default execution timeout (seconds) | 300 |
| `AGENTSPAN_LLM_RETRY_COUNT` | LLM task retry count | 3 |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | Worker poll interval (ms) | 100 |
| `AGENTSPAN_WORKER_THREADS` | Worker threads per tool | 1 |

> **Note:** The legacy `CONDUCTOR_*` prefixed variables are still accepted for backward compatibility.

## Dependencies

- **Required:** `conductor-python>=1.1.10`
- **Optional:** `pydantic` (structured output), `openai` (GPTAssistantAgent), `litellm` (LLMGuardrail), `opentelemetry-api` + `opentelemetry-sdk` (tracing), `jupyter_client` + `ipykernel` (JupyterCodeExecutor)
- **Dev:** `pytest>=7.0`, `pytest-asyncio>=0.21`, `ruff>=0.4`, `mypy>=1.10`
