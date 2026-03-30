# AgentSpan Worker Types

Workers are functions registered as Conductor task pollers. They execute locally (SDK-side)
while execution orchestration happens server-side. Both Python and TypeScript SDKs implement
all worker types with identical behavior.

## Quick Reference

| # | Worker Type | Task Name Pattern | Trigger |
|---|-------------|-------------------|---------|
| 1 | Tool | `{tool_name}` | `agent.tools` with `tool_type == "worker"` |
| 2 | CLI Command | `{agent_name}_run_command` | `agent.cli_commands == True` |
| 3 | Code Execution | `{agent_name}_execute_code` | `agent.local_code_execution == True` |
| 4 | Output Guardrail (combined) | `{agent_name}_output_guardrail` | Custom guardrails (local compile path) |
| 5 | Individual Guardrail | `{guardrail.name}` | Custom guardrails (server compile path) |
| 6 | Stop When | `{agent_name}_stop_when` | `agent.stop_when` is callable |
| 7 | Gate | `{agent_name}_gate` | `agent.gate` is callable |
| 8 | Callback | `{agent_name}_{position}` | `agent.callbacks` |
| 9 | Termination | `{agent_name}_termination` | `agent.termination` is set |
| 10 | Check Transfer | `{agent_name}_check_transfer` | Hybrid or swarm agent |
| 11 | Router Function | `{agent_name}_router_fn` | `strategy == "router"` with callable router |
| 12 | Handoff Check | `{agent_name}_handoff_check` | `agent.handoffs` is non-empty |
| 13 | Swarm Transfer | `{source_agent}_transfer_to_{peer}` | `strategy == "swarm"` with sub-agents |
| 14 | Manual Selection | `{agent_name}_process_selection` | `strategy == "manual"` with sub-agents |
| 15 | Framework | `{worker.name}` | Foreign framework with extractable tools |
| 16 | Framework Passthrough | `{worker_name}` | Foreign framework (passthrough) |
| 17 | Claude Code Passthrough | `{agent_name}` | `model="claude-code/..."` |

## Task Definition Registration

**Task definitions are registered by the server during agent compilation.** SDKs do NOT register
task definitions — they only poll for tasks. The server returns `requiredWorkers` in the
start/deploy response so SDKs know exactly which workers to register.

| Setting              | Value          | Source |
|----------------------|----------------|--------|
| `timeoutSeconds`     | 0 (no timeout) | `AgentService.registerTaskDef()` |
| `responseTimeoutSeconds` | 3600 (1 hour) | Conductor requires minimum 1s |
| Retry count          | 2              | Server-side |
| Retry logic          | LINEAR_BACKOFF | Server-side |
| Retry delay          | 2 s            | Server-side |

## Task Name Prefixing Rules

All auto-generated task names MUST be prefixed with the agent name to prevent collisions
when multiple agents share the same Conductor namespace.

| Category | Pattern | Example |
|---|---|---|
| System workers | `{agentName}_{type}` | `my_agent_termination` |
| CLI tools | `{agentName}_run_command` | `git_fetch_run_command` |
| Code execution | `{agentName}_execute_code` | `coder_execute_code` |
| Swarm transfers | `{sourceAgent}_transfer_to_{peer}` | `coder_transfer_to_qa_tester` |
| User-defined tools | `{tool_name}` (user-controlled) | `get_weather` |

## Credentials

Credentials are always resolved from the server. There is no environment variable fallback.

- **Execution token present** → `POST /api/credentials/resolve` → injected into `process.env`/`os.environ`
- **No execution token** → `FAILED_WITH_TERMINAL_ERROR` (non-retryable)
- **Credentials not found on server** → `FAILED_WITH_TERMINAL_ERROR` (non-retryable)
- **Cleanup** → credentials removed from environment after tool execution

Store credentials with: `agentspan credentials set --name <NAME>`

## TypeScript Parity

Both Python and TypeScript SDKs implement all 17 worker types. The TypeScript SDK includes:
- All SWARM workers (transfer_to, check_transfer, handoff_check, process_selection)
- Claude Code agent support (`ClaudeCode` class, `PermissionMode` enum)
- CLI command execution (`CliConfig`, `makeCliTool()`)
- Code execution validators (`CommandValidator`)
- LLM guardrails (`LLMGuardrail` class)
- Credential resolution and injection (`resolveCredentials`, `injectCredentials`)

## Worker Lifecycle

1. **Server compilation** — Server compiles agent → registers all task definitions → returns `requiredWorkers` list
2. **SDK registration** — SDK registers workers (poll functions) for task names in `requiredWorkers`
3. **Polling** — Workers poll Conductor for tasks, execute functions, report results
4. **Credentials** — Before tool execution, credentials are resolved from server and injected
5. **Monitoring** — TaskHandler checks process health every 5s and restarts dead workers
6. **Shutdown** — Workers stopped during `AgentRuntime.shutdown()`
