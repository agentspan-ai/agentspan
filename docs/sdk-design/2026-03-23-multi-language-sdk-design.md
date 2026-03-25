# Multi-Language SDK Design Spec

**Date:** 2026-03-23
**Status:** Complete
**Approach:** Reference Implementation + Translation Guide (Approach 2)

## Deliverable Status

| # | File | Status |
|---|------|--------|
| 1 | [base-design.md](2026-03-23-multi-language-sdk-design.md) | Complete |
| 2 | [kitchen-sink.md](kitchen-sink.md) | Complete |
| 3 | [kitchen_sink.py](../../sdk/python/examples/kitchen_sink.py) | Complete |
| 4 | [typescript.md](typescript.md) | Complete |
| 5 | [go.md](go.md) | Complete |
| 6 | [java.md](java.md) | Complete |
| 7 | [kotlin.md](kotlin.md) | Complete |
| 8 | [csharp.md](csharp.md) | Complete |
| 9 | [ruby.md](ruby.md) | Complete |

---

## 1. Overview

Agentspan provides a server-first agent execution platform built on Conductor. The Python SDK is the reference implementation. This spec defines how to replicate full feature parity in **TypeScript**, **Go**, **Java** (records + POJOs), **Kotlin**, **C#**, and **Ruby**.

### 1.1 Architecture Model

```
┌─────────────────────────────────────────────────┐
│                   SDK (any language)             │
│                                                  │
│  Agent Definition → Serialization → AgentConfig  │
│  Worker Poll Loop → Tool Execution → Results     │
│  SSE Client → Event Stream → AgentStream         │
│  Credential Fetcher → Execution Token → Secrets  │
└──────────────────────┬──────────────────────────┘
                       │ REST + SSE (JSON)
┌──────────────────────▼──────────────────────────┐
│              Agentspan Server (Java)             │
│                                                  │
│  Compiler → Conductor WorkflowDef                │
│  Executor → Conductor Workflow Engine             │
│  StreamRegistry → SSE Events                     │
│  CredentialService → AES-256-GCM Store           │
└─────────────────────────────────────────────────┘
```

Every SDK's job is the same:
1. **Define** agents, tools, guardrails as language-native constructs
2. **Serialize** to the AgentConfig JSON format the server expects
3. **Register** tool/guardrail/callback workers that the server can dispatch to
4. **Execute** via REST API (start, deploy, compile, status, respond)
5. **Stream** via SSE for real-time events
6. **Resolve** credentials via execution tokens at runtime

### 1.2 Design Principle

The Python SDK **is** the spec. Each language SDK must:
- Produce identical AgentConfig JSON for equivalent agent definitions
- Register equivalent Conductor workers for tools/guardrails/callbacks
- Handle identical SSE event streams
- Pass the same kitchen sink acceptance test

### 1.3 Deliverables

| # | File | Purpose |
|---|------|---------|
| 1 | `docs/sdk-design/base-design.md` | This document — protocol, conceptual model, feature matrix |
| 2 | `docs/sdk-design/kitchen-sink.md` | Kitchen sink scenario spec + expected behavior + judge rubrics |
| 3 | `docs/sdk-design/kitchen-sink.py` | Working Python kitchen sink implementation |
| 4 | `docs/sdk-design/typescript.md` | TypeScript idiom translation guide |
| 5 | `docs/sdk-design/go.md` | Go idiom translation guide |
| 6 | `docs/sdk-design/java.md` | Java idiom guide (record 16+ and POJO 8+ patterns) |
| 7 | `docs/sdk-design/kotlin.md` | Kotlin idiom translation guide |
| 8 | `docs/sdk-design/csharp.md` | C# idiom translation guide |
| 9 | `docs/sdk-design/ruby.md` | Ruby idiom translation guide |

---

## 2. Protocol Specification

### 2.1 Authentication

Two supported modes:

| Mode | Headers | Use Case |
|------|---------|----------|
| API Key (preferred) | `Authorization: Bearer <api_key>` | Production |
| Legacy Key/Secret | `X-Auth-Key: <key>`, `X-Auth-Secret: <secret>` | Backward compat |

### 2.2 REST API Endpoints

Base URL: `{server_url}/agent` (server_url defaults to `http://localhost:8080/api`)

#### POST /agent/start — Start Agent Execution

Compiles the agent config, registers workflow + tasks, starts execution.

**Request:**
```json
{
  "agentConfig": { ... },
  "prompt": "User input text",
  "sessionId": "optional-session-id",
  "media": ["optional-image-url"],
  "idempotencyKey": "optional-dedup-key",
  "timeoutSeconds": 300
}
```

For framework agents (LangGraph, LangChain, OpenAI, Google ADK, Vercel AI SDK):
```json
{
  "framework": "langgraph|langchain|openai|google_adk|vercel_ai",
  "rawConfig": { ... },
  "prompt": "User input text",
  "sessionId": "optional-session-id"
}
```

**Response:**
```json
{
  "workflowId": "uuid-string",
  "workflowName": "agent_name"
}
```

#### POST /agent/compile — Compile Only (No Execution)

Same request as `/start`, returns compiled WorkflowDef without executing.

**Response:**
```json
{
  "workflowDef": { ... }
}
```

#### POST /agent/deploy — Deploy (Compile + Register)

Registers the workflow and task definitions for later execution. CI/CD operation.

**Request:** Same as `/start`.

**Response:**
```json
{
  "workflowName": "agent_name",
  "workflowDef": { ... }
}
```

Note: Unlike `/start`, deploy does NOT return a `workflowId` because no execution is started.

#### GET /agent/{workflowId}/status — Poll Status

**Response:**
```json
{
  "workflowId": "...",
  "status": "RUNNING|COMPLETED|FAILED|TERMINATED|TIMED_OUT|PAUSED",
  "isComplete": true,
  "isRunning": false,
  "isWaiting": false,
  "output": { "result": "..." },
  "currentTask": "task_ref_name",
  "messages": [...],
  "pendingTool": { "name": "...", "args": {...} },
  "tokenUsage": {
    "promptTokens": 100,
    "completionTokens": 50,
    "totalTokens": 150
  }
}
```

#### POST /agent/{workflowId}/respond — HITL Response

**Request:**
```json
{ "approved": true }
```
or
```json
{ "approved": false, "reason": "Not appropriate" }
```
or
```json
{ "message": "Please revise the introduction" }
```

#### GET /agent/stream/{workflowId} — SSE Event Stream

Returns `text/event-stream`. Supports reconnection via `Last-Event-ID` header.

**SSE Wire Format:**
```
id: 1
event: thinking
data: {"type":"thinking","content":"Let me analyze...","workflowId":"...","timestamp":1234567890}

id: 2
event: tool_call
data: {"type":"tool_call","toolName":"search","args":{"query":"..."},"workflowId":"...","timestamp":1234567890}

id: 3
event: tool_result
data: {"type":"tool_result","toolName":"search","result":{"items":[...]},"workflowId":"...","timestamp":1234567890}

:heartbeat

id: 4
event: done
data: {"type":"done","output":{"result":"..."},"workflowId":"...","timestamp":1234567890}
```

**Event Types:**

**SDK EventType enum (must be in every SDK):**

| Type | Fields | Description |
|------|--------|-------------|
| `thinking` | content | LLM reasoning text |
| `tool_call` | toolName, args | Tool invocation |
| `tool_result` | toolName, result | Tool response |
| `guardrail_pass` | guardrailName, content | Guardrail passed |
| `guardrail_fail` | guardrailName, content | Guardrail failed |
| `waiting` | pendingTool | HITL pause (tool awaiting approval) |
| `handoff` | target | Agent handoff |
| `message` | content | Assistant message text |
| `error` | content | Error occurred |
| `done` | output | Workflow completed |

**Server-only event types (pass through, not in EventType enum):**

These may appear on the SSE stream but are not part of the SDK's EventType enum. SDKs should forward them as raw events:

| Type | Fields | Description |
|------|--------|-------------|
| `context_condensed` | content | Context window condensation |
| `subagent_start` | workflowId | Sub-agent workflow started |
| `subagent_stop` | workflowId | Sub-agent workflow completed |

**Heartbeat:** Comment lines (`:heartbeat`) every 15 seconds. Not real events — used to keep connection alive.

**Reconnection:** Client sends `Last-Event-ID: <last_id>` header. Server replays missed events from buffer (200 events, 5-min retention).

#### POST /agent/{workflowId}/events — Framework Worker Event Push

For framework agent workers to push intermediate events back to the server for SSE forwarding.

**Request:**
```json
{
  "events": [
    {"type": "tool_call", "toolName": "search", "args": {...}},
    {"type": "tool_result", "toolName": "search", "result": {...}}
  ]
}
```

#### GET /agent/list — List Registered Agents

**Response:** Array of agent metadata objects.

#### GET /agent/executions — Search Executions

**Query params:** `agentName`, `status`, `sessionId`

#### GET /agent/execution/{workflowId} — Detailed Execution

Full workflow with task list, token usage, sub-workflow details.

#### DELETE /agent/{name} — Delete Agent Definition

### 2.3 Configuration

SDKs must support configuration via environment variables:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:8080/api` | Server API URL |
| `AGENTSPAN_API_KEY` | — | Bearer token / API key |
| `AGENTSPAN_AUTH_KEY` | — | Legacy auth key |
| `AGENTSPAN_AUTH_SECRET` | — | Legacy auth secret |
| `AGENTSPAN_LLM_RETRY_COUNT` | `3` | LLM call retry count |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_WORKER_THREADS` | `1` | Threads per worker |
| `AGENTSPAN_AUTO_START_WORKERS` | `true` | Auto-start worker processes |
| `AGENTSPAN_AUTO_START_SERVER` | `true` | Auto-start local server |
| `AGENTSPAN_DAEMON_WORKERS` | `true` | Kill workers on exit |
| `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | `false` | Auto-register LLM integrations |
| `AGENTSPAN_STREAMING_ENABLED` | `true` | Enable SSE streaming |
| `AGENTSPAN_CREDENTIAL_STRICT_MODE` | `false` | No env var fallback for credentials |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | Logging level |

**URL normalization:** If `server_url` does not end with `/api`, append it automatically.

---

## 3. AgentConfig Serialization Format

This is the JSON structure that every SDK must produce when serializing an Agent tree. The server compiles this into a Conductor WorkflowDef. **Producing identical JSON for equivalent agent definitions is the primary correctness criterion.**

### 3.1 Top-Level AgentConfig

```json
{
  "name": "agent_name",
  "model": "provider/model_name",
  "strategy": "handoff|sequential|parallel|router|round_robin|random|swarm|manual",
  "maxTurns": 25,
  "timeoutSeconds": 300,
  "external": false,
  "instructions": "string | { prompt_template } | null",
  "tools": [ ToolConfig... ],
  "agents": [ AgentConfig... ],
  "router": "AgentConfig | { taskName: string }",
  "outputType": { "schema": {...}, "className": "MyModel" },
  "guardrails": [ GuardrailConfig... ],
  "memory": { "messages": [...], "maxMessages": 50 },
  "maxTokens": 4096,
  "temperature": 0.7,
  "stopWhen": { "taskName": "agent_name_stop_when" },
  "termination": TerminationConfig,
  "handoffs": [ HandoffConfig... ],
  "allowedTransitions": { "agent_a": ["agent_b", "agent_c"] },
  "introduction": "I am agent X, I specialize in...",
  "metadata": { "key": "value" },
  "planner": true,
  "callbacks": [ { "position": "before_agent", "taskName": "agent_name_before_agent" } ],
  "includeContents": "default|none",
  "thinkingConfig": { "enabled": true, "budgetTokens": 1024 },
  "requiredTools": ["tool_a", "tool_b"],
  "gate": GateConfig,
  "codeExecution": {
    "enabled": true,
    "allowedLanguages": ["python", "shell"],
    "allowedCommands": ["python3", "pip"],
    "timeout": 30
  },
  "cliConfig": {
    "enabled": true,
    "allowedCommands": ["git", "gh"],
    "timeout": 30,
    "allowShell": false
  },
  "credentials": ["GITHUB_TOKEN", "OPENAI_API_KEY"]
}
```

**Rules:**
- All keys are **camelCase**
- Omit keys with `null` values (cleaner JSON)
- Recursive: `agents` array contains nested AgentConfig objects
- `strategy` is only set when `agents` is non-empty

### 3.2 ToolConfig

```json
{
  "name": "tool_name",
  "description": "What the tool does",
  "inputSchema": {
    "type": "object",
    "properties": { "city": { "type": "string" } },
    "required": ["city"]
  },
  "toolType": "worker|http|api|mcp|agent_tool|human|generate_image|generate_audio|generate_video|generate_pdf|rag_search|rag_index",
  "outputSchema": { ... },
  "approvalRequired": true,
  "timeoutSeconds": 120,
  "config": {
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": { "Authorization": "Bearer ${API_KEY}" },
    "credentials": ["API_KEY"]
  },
  "guardrails": [ GuardrailConfig... ]
}
```

**Tool Types:**

| toolType | Conductor Task | Worker Needed | Description |
|----------|---------------|---------------|-------------|
| `worker` | SIMPLE | Yes (SDK) | Native `@tool` function executed by SDK worker |
| `http` | HTTP | No | Server-side HTTP call (single endpoint) |
| `api` | HTTP (via LIST_API_TOOLS discovery) | No | Auto-discovered from OpenAPI/Swagger/Postman spec |
| `mcp` | CALL_MCP_TOOL | No | Model Context Protocol tool |
| `agent_tool` | SUB_WORKFLOW | Depends | Nested agent as tool |
| `human` | HUMAN | No | Human-in-the-loop tool |
| `generate_image` | GENERATE_IMAGE | No | Server-side image generation |
| `generate_audio` | GENERATE_AUDIO | No | Server-side audio generation |
| `generate_video` | GENERATE_VIDEO | No | Server-side video generation |
| `generate_pdf` | GENERATE_PDF | No | Server-side PDF generation |
| `rag_search` | LLM_SEARCH_INDEX | No | Vector search (RAG) |
| `rag_index` | LLM_INDEX_TEXT | No | Vector index (RAG) |

**External/by-reference tools:** When `toolType` is `worker` but no function is registered, the SDK emits just the task name. A remote worker running elsewhere picks up the task. The SDK does not need to register a local worker.

### 3.3 GuardrailConfig

```json
{
  "name": "guardrail_name",
  "position": "input|output",
  "onFail": "retry|raise|fix|human",
  "maxRetries": 3,
  "guardrailType": "regex|llm|custom|external",
  "patterns": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
  "mode": "block|allow",
  "message": "Custom failure message",
  "model": "openai/gpt-4o",
  "policy": "Check if output contains harmful content",
  "maxTokens": 100,
  "taskName": "guardrail_worker_name"
}
```

| guardrailType | Execution | Fields Used |
|---------------|-----------|-------------|
| `regex` | Server-side INLINE (JavaScript) | patterns, mode, message |
| `llm` | Server-side LLM_CHAT_COMPLETE | model, policy, maxTokens |
| `custom` | SDK worker (SIMPLE task) | taskName |
| `external` | Remote worker (SIMPLE task) | taskName (no local worker) |

### 3.4 TerminationConfig

Composable with AND/OR operators:

```json
{ "type": "text_mention", "text": "DONE", "caseSensitive": false }
{ "type": "stop_message", "stopMessage": "TERMINATE" }
{ "type": "max_message", "maxMessages": 50 }
{ "type": "token_usage", "maxTotalTokens": 100000, "maxPromptTokens": 80000, "maxCompletionTokens": 20000 }
{ "type": "and", "conditions": [ TerminationConfig, TerminationConfig ] }
{ "type": "or", "conditions": [ TerminationConfig, TerminationConfig ] }
```

### 3.5 HandoffConfig

```json
{ "target": "agent_name", "type": "on_tool_result", "toolName": "search", "resultContains": "found" }
{ "target": "agent_name", "type": "on_text_mention", "text": "TRANSFER" }
{ "target": "agent_name", "type": "on_condition", "taskName": "agent_handoff_target" }
```

### 3.6 PromptTemplate (Instructions)

```json
{
  "type": "prompt_template",
  "name": "template_name",
  "variables": { "domain": "tech" },
  "version": 1
}
```

### 3.7 GateConfig (Sequential Pipeline Gates)

```json
{ "type": "text_contains", "text": "APPROVED", "caseSensitive": true }
{ "taskName": "agent_name_gate" }
```

### 3.8 OutputType

```json
{
  "schema": {
    "type": "object",
    "properties": {
      "title": { "type": "string" },
      "score": { "type": "number" }
    },
    "required": ["title", "score"]
  },
  "className": "ArticleScore"
}
```

---

## 4. Conceptual Model — SDK Public API

Every SDK must expose the following public API surface. Names should follow the target language's conventions (e.g., `snake_case` in Python/Ruby, `camelCase` in JS/Java/Kotlin, `PascalCase` in C#, etc.) but the semantics must be identical.

### 4.1 Core Types

#### Agent

The single orchestration primitive. Every agent — simple or complex — is an instance of this class.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Unique agent name |
| `model` | string | null | LLM model identifier (`provider/model`) |
| `instructions` | string \| callable \| PromptTemplate | null | System prompt |
| `tools` | Tool[] | [] | Tools available to this agent |
| `agents` | Agent[] | [] | Sub-agents (multi-agent) |
| `strategy` | Strategy enum | null | Orchestration strategy |
| `router` | Agent \| callable | null | Router for `router` strategy |
| `output_type` | class/schema | null | Structured output type |
| `guardrails` | Guardrail[] | [] | Input/output validators |
| `memory` | ConversationMemory | null | Conversation history |
| `max_turns` | int | 25 | Max LLM call turns |
| `max_tokens` | int | null | Max tokens per LLM call |
| `temperature` | float | null | LLM temperature |
| `timeout_seconds` | int | 0 | Workflow timeout (0 = no timeout) |
| `external` | bool | false | True if this agent runs elsewhere |
| `stop_when` | callable | null | Custom stop condition |
| `termination` | TerminationCondition | null | Composable stop condition |
| `handoffs` | HandoffCondition[] | [] | Handoff triggers |
| `allowed_transitions` | map[string, string[]] | null | Transition constraints |
| `introduction` | string | null | Agent self-introduction |
| `metadata` | map | null | Arbitrary metadata |
| `callbacks` | CallbackHandler[] | [] | Lifecycle hooks |
| `planner` | bool | false | Enable planning mode |
| `include_contents` | string | null | Controls parent context for sub-agents: `"default"` passes full context, `"none"` gives fresh context |
| `thinking_budget_tokens` | int | null | Extended thinking budget |
| `required_tools` | string[] | null | Tools the LLM must use |
| `gate` | GateCondition | null | Pipeline gate condition |
| `code_execution_config` | CodeExecutionConfig | null | Code sandbox config |
| `cli_config` | CliConfig | null | CLI tool config |
| `credentials` | (string \| CredentialFile)[] | null | Agent-level credentials |

**Chaining operator:** `agent_a >> agent_b >> agent_c` creates a sequential pipeline. SDK must support this via operator overloading or a builder pattern.

#### Strategy Enum

```
HANDOFF, SEQUENTIAL, PARALLEL, ROUTER, ROUND_ROBIN, RANDOM, SWARM, MANUAL
```

#### PromptTemplate

Reference to a server-managed prompt template:
- `name`: template name
- `variables`: key-value map for template variables
- `version`: template version (optional)

### 4.2 Tool System

#### @tool Decorator / Tool Registration

Registers a function as a Conductor SIMPLE task. The SDK must:
1. Extract function name, docstring, and parameter schema (via type hints or equivalent)
2. Generate JSON Schema for the input parameters
3. Register a Conductor task definition
4. Start a worker thread/goroutine/fiber that polls for and executes the task

#### TypeScript SDK: Superset Tool Compatibility

The TypeScript SDK is a **superset** — it accepts both Vercel AI SDK-style tool definitions (Zod schemas) and agentspan-native tool definitions (JSON Schema), auto-detecting which format was passed:

1. **Zod schema detection:** If `inputSchema` is a ZodType instance (has `._def` property), convert to JSON Schema via `zodToJsonSchema()` at serialization time
2. **JSON Schema passthrough:** If `inputSchema` is a plain object with `type: "object"`, use as-is
3. **Vercel AI SDK `tool()` objects:** If a tool has `inputSchema` as Zod + `execute` function (matching `ai` package's `tool()` shape), extract and wrap as agentspan tool
4. **Mixed arrays:** An agent's `tools` array can contain a mix of all formats

This means a user can do:
```typescript
import { tool } from '@agentspan/sdk';
import { tool as aiTool } from 'ai';
import { z } from 'zod';

// Agentspan native (JSON Schema)
const t1 = tool(fn, { inputSchema: { type: 'object', properties: { city: { type: 'string' } } } });

// Agentspan with Zod (auto-converted)
const t2 = tool(fn, { inputSchema: z.object({ city: z.string() }) });

// Vercel AI SDK tool (auto-detected and wrapped)
const t3 = aiTool({ description: 'Get weather', inputSchema: z.object({ city: z.string() }), execute: fn });

// All three work in the same agent
const agent = new Agent({ name: 'test', tools: [t1, t2, t3] });
```

**Python reference:**
```python
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"
```

**Tool decorator options:**
- `name`: override tool name (default: function name)
- `external`: bool (default: false) — when true, no local worker is started; only the schema is emitted. Conductor dispatches to external workers polling for that task name.
- `approval_required`: bool (default: false) — HITL gate before execution
- `timeout_seconds`: int — per-invocation timeout
- `guardrails`: list — tool-level input guardrails
- `isolated`: bool (default: true) — controls credential isolation. When true, tool runs in subprocess with credentials as env vars. When false, tool runs in-process.
- `credentials`: list — credential names this tool needs

#### ToolContext (Dependency Injection)

When a tool function declares a `ToolContext` parameter, the SDK injects execution context:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session identifier |
| `workflow_id` | string | Conductor workflow ID |
| `agent_name` | string | Calling agent's name |
| `metadata` | map | Agent metadata |
| `dependencies` | map | Injected dependencies |
| `state` | map | Shared state |

The server passes `__agentspan_ctx__` in the task input. The SDK extracts and populates ToolContext from it.

#### Tool Constructors (Server-Side Tools)

These create tools that execute on the server — no local worker needed:

| Constructor | Purpose | Full Signature |
|-------------|---------|----------------|
| `http_tool` | HTTP API call | `(name, description, url, method="GET", headers=None, input_schema=None, accept=["application/json"], content_type="application/json", credentials=None)` |
| `api_tool` | Auto-discover from OpenAPI/Swagger/Postman | `(url, name=None, description=None, headers=None, tool_names=None, max_tools=64, credentials=None)` |
| `mcp_tool` | MCP protocol tool | `(server_url, name=None, description=None, headers=None, tool_names=None, max_tools=64, credentials=None)` |
| `agent_tool` | Sub-agent as tool | `(agent, name=None, description=None, retry_count=None, retry_delay_seconds=None, optional=None)` |
| `human_tool` | Human-in-the-loop tool | `(name, description, input_schema=None)` |
| `image_tool` | Image generation | `(name, description, llm_provider, model, input_schema=None, **defaults)` |
| `audio_tool` | Audio generation | `(name, description, llm_provider, model, input_schema=None, **defaults)` |
| `video_tool` | Video generation | `(name, description, llm_provider, model, input_schema=None, **defaults)` |
| `pdf_tool` | PDF generation | `(name="generate_pdf", description="Generate a PDF...", input_schema=None, **defaults)` |
| `search_tool` | Vector search (RAG) | `(name, description, vector_db, index, embedding_model_provider, embedding_model, namespace="default_ns", max_results=5, dimensions=None, input_schema=None)` |
| `index_tool` | Vector index (RAG) | `(name, description, vector_db, index, embedding_model_provider, embedding_model, namespace="default_ns", chunk_size=None, chunk_overlap=None, dimensions=None, input_schema=None)` |

**Note on `http_tool` credential headers:** Headers can reference credentials using `${NAME}` syntax (e.g., `"Authorization": "Bearer ${API_KEY}"`). The server resolves these at execution time from the credential store. All placeholder names must be declared in the `credentials` list.

**Note on `api_tool`:** Mirrors the `mcp_tool()` pattern. Points to an OpenAPI/Swagger/Postman spec URL (or base URL for auto-discovery). Server fetches and parses the spec at workflow startup via `LIST_API_TOOLS` system task, discovers all operations as individual tools, and executes them as standard HTTP tasks. If discovered operations exceed `max_tools`, a lightweight LLM selects the most relevant ones based on the user's prompt. See `docs/sdk-design/2026-03-23-api-tool-design.md` for full design.

#### External / By-Reference Tools

Tools with no local function — the SDK emits just the task name in the AgentConfig. A remote worker running on another machine picks up the task via Conductor's task queue.

```python
# Python: external tool (no function body)
my_tool = tool(name="remote_formatter", description="...", input_schema={...}, external=True)
```

Every SDK must support defining tools by reference (name + schema only, no implementation).

### 4.3 Guardrail System

#### @guardrail Decorator / Guardrail Registration

Custom guardrails are functions that return a `GuardrailResult`:

```python
@guardrail(name="pii_check", position="output", on_fail="retry")
def check_pii(output: str) -> GuardrailResult:
    if has_pii(output):
        return GuardrailResult(passed=False, message="PII detected")
    return GuardrailResult(passed=True)
```

#### GuardrailResult

| Field | Type | Description |
|-------|------|-------------|
| `passed` | bool | Whether validation passed |
| `message` | string | Failure reason |
| `fixed_output` | string | Corrected output (for `on_fail=fix`) |

#### Built-In Guardrails

| Class | Execution | Description |
|-------|-----------|-------------|
| `RegexGuardrail` | Server-side (INLINE JS) | Pattern matching with block/allow mode |
| `LLMGuardrail` | Server-side (LLM call) | AI-powered policy checking |

#### External / By-Reference Guardrails

Guardrails with `external=True` — the SDK emits just the task name. A remote guardrail worker picks it up.

#### OnFail Enum

```
RETRY — Re-run the LLM with the guardrail feedback
RAISE — Fail the workflow
FIX   — Use guardrail's fixed_output as the result
HUMAN — Pause for human review
```

#### Position Enum

```
INPUT  — Validate before LLM call
OUTPUT — Validate after LLM call
```

### 4.4 Result Types

#### AgentResult (returned by run())

| Field | Type | Description |
|-------|------|-------------|
| `output` | any (dict) | Final output — always dict with `result` key |
| `workflow_id` | string | Conductor workflow ID |
| `correlation_id` | string | Optional correlation ID |
| `messages` | Message[] | Full conversation history |
| `tool_calls` | ToolCall[] | All tool invocations |
| `status` | Status enum | Terminal status |
| `finish_reason` | FinishReason enum | Why the agent stopped |
| `error` | string | Error message (on failure) |
| `token_usage` | TokenUsage | Aggregated token metrics |
| `metadata` | map | Execution metadata |
| `events` | AgentEvent[] | All captured events |
| `sub_results` | map[string, any] | Per-agent results (parallel strategy) |

**Convenience properties:** `is_success`, `is_failed`, `is_rejected`

#### Status Enum

```
COMPLETED, FAILED, TERMINATED, TIMED_OUT
```

#### FinishReason Enum

```
STOP, LENGTH, TOOL_CALLS, ERROR, CANCELLED, TIMEOUT, GUARDRAIL, REJECTED
```

#### TokenUsage

```
prompt_tokens: int, completion_tokens: int, total_tokens: int
```

#### AgentHandle (returned by start())

A handle to a running workflow. Supports:

| Method | Description |
|--------|-------------|
| `get_status()` | Poll current status → AgentStatus |
| `respond(output)` | Complete HITL task with arbitrary output |
| `approve()` | Approve pending tool call |
| `reject(reason)` | Reject pending tool call |
| `send(message)` | Send message to waiting agent |
| `pause()` | Pause workflow |
| `resume()` | Resume paused workflow |
| `cancel(reason)` | Cancel workflow |
| `stream()` | Get AgentStream for this workflow |

Every method must have both sync and async variants.

#### AgentStatus (returned by get_status())

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | string | Conductor workflow ID |
| `is_complete` | bool | Terminal state reached |
| `is_running` | bool | Still executing |
| `is_waiting` | bool | Paused (HITL) |
| `output` | any | Available when complete |
| `status` | string | Raw Conductor status |
| `reason` | string | Failure/termination reason |
| `current_task` | string | Currently executing task |
| `messages` | Message[] | Conversation so far |
| `pending_tool` | map | Tool awaiting approval |

#### AgentEvent (yielded by stream)

| Field | Type | Description |
|-------|------|-------------|
| `type` | EventType enum | Event type |
| `content` | string | Text content |
| `tool_name` | string | Tool name |
| `args` | map | Tool arguments |
| `result` | any | Tool result |
| `target` | string | Handoff target |
| `output` | any | Final output (done event) |
| `workflow_id` | string | Workflow ID |
| `guardrail_name` | string | Guardrail name |

#### EventType Enum

```
THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING, MESSAGE, ERROR, DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL
```

Note: Server-only event types (`context_condensed`, `subagent_start`, `subagent_stop`) are NOT in this enum. SDKs should pass them through as raw events.

#### AgentStream / AsyncAgentStream

Iterable/async-iterable over AgentEvent. After iteration:
- `events` — list of all captured events
- `result` — AgentResult built from events
- `get_result()` — drain stream and return result

Also exposes HITL methods: `respond()`, `approve()`, `reject()`, `send()`

#### DeploymentInfo

```
workflow_name: string, agent_name: string
```

### 4.5 Execution API

Every SDK must provide these functions. Each function operates on a **singleton runtime** (lazily initialized) or accepts an explicit runtime.

| Function | Description | Returns |
|----------|-------------|---------|
| `configure(config)` | Pre-configure the singleton runtime | void |
| `run(agent, prompt)` | Execute synchronously, block until done | AgentResult |
| `run_async(agent, prompt)` | Execute asynchronously | Future<AgentResult> |
| `start(agent, prompt)` | Start without waiting | AgentHandle |
| `start_async(agent, prompt)` | Start asynchronously | Future<AgentHandle> |
| `stream(agent, prompt)` | Stream events synchronously | AgentStream |
| `stream_async(agent, prompt)` | Stream events asynchronously | AsyncAgentStream |
| `deploy(agent)` | Compile + register (no execution) | DeploymentInfo |
| `deploy_async(agent)` | Deploy asynchronously | Future<DeploymentInfo> |
| `serve()` | Start workflow server (blocking) | void |
| `plan(agent)` | Compile-only dry-run preview (no prompt, no execution) | ExecutionPlan |
| `shutdown()` | Shutdown singleton runtime | void |

**Context Manager / Resource Management:** The runtime must support language-appropriate resource management (Python `with`, Java `try-with-resources`, Go `defer`, C# `using`, Ruby `ensure`, etc.).

### 4.6 AgentRuntime

The runtime class manages:
1. **HTTP client** — async HTTP for all API calls
2. **Worker manager** — registers and runs Conductor workers for tools/guardrails/callbacks
3. **SSE client** — connects to event stream with reconnection
4. **Credential fetcher** — resolves credentials via execution tokens
5. **Configuration** — from environment or explicit config

**Lifecycle:**
```
init → configure → [register workers] → [execute] → shutdown
```

Every SDK's runtime must:
- Start workers automatically when the first agent is executed (if `auto_start_workers=true`)
- Auto-start the local server if configured (if `auto_start_server=true`)
- Clean up workers on shutdown
- Support both singleton and instance-based usage

### 4.7 Memory

#### ConversationMemory

Session-level conversation history:

| Method | Description |
|--------|-------------|
| `add_user_message(content)` | Add user message |
| `add_assistant_message(content)` | Add assistant message |
| `add_system_message(content)` | Add system message |
| `add_tool_call(name, args)` | Add tool call record |
| `add_tool_result(name, result)` | Add tool result record |
| `to_chat_messages()` | Convert to LLM message format |
| `clear()` | Clear all messages |

**Max message windowing:** When `max_messages` is set, trim oldest messages but always preserve system messages.

**Serialization:** Memory serializes as `{ "messages": [...], "maxMessages": N }` in AgentConfig.

#### SemanticMemory

Cross-session long-term memory with vector search:

| Method | Description |
|--------|-------------|
| `add(content, metadata)` | Store a memory entry |
| `search(query, top_k)` | Retrieve similar memories |
| `delete(id)` | Remove a memory |
| `clear()` | Remove all memories |
| `list_all()` | List all entries |

**MemoryStore (pluggable backend):** Abstract interface. SDK must provide at least `InMemoryStore` (keyword-overlap similarity).

### 4.8 Termination Conditions

Composable with `&` (AND) and `|` (OR) operators:

| Condition | Parameters | Description |
|-----------|-----------|-------------|
| `TextMentionTermination` | text, case_sensitive (default: false) | Stop when text appears in output |
| `StopMessageTermination` | stop_message | Stop on specific message |
| `MaxMessageTermination` | max_messages | Stop after N messages |
| `TokenUsageTermination` | max_total, max_prompt, max_completion | Stop on token budget |

**Composition:**
```python
# Python
condition = TextMentionTermination("DONE") | (MaxMessageTermination(50) & TokenUsageTermination(100000))
```

Every SDK must support this composition pattern using operator overloading or builder pattern.

### 4.9 Handoff Conditions

| Condition | Parameters | Description |
|-----------|-----------|-------------|
| `OnToolResult` | target, tool_name, result_contains | Handoff after specific tool result |
| `OnTextMention` | target, text | Handoff when output contains text |
| `OnCondition` | target, callable | Custom handoff logic |

### 4.10 Code Execution

#### CodeExecutionConfig

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | true | Enable code execution |
| `allowed_languages` | ["python"] | Languages the agent can execute |
| `allowed_commands` | [] | CLI commands allowed |
| `timeout` | 30 | Execution timeout (seconds) |

#### CodeExecutor (Abstract Base)

| Method | Description |
|--------|-------------|
| `execute(code, language)` | Run code, return ExecutionResult |
| `as_tool()` | Convert executor to an agent tool |

#### Implementations

| Class | Description |
|-------|-------------|
| `LocalCodeExecutor` | Subprocess execution |
| `DockerCodeExecutor` | Docker container execution |
| `JupyterCodeExecutor` | Jupyter kernel execution |
| `ServerlessCodeExecutor` | Remote function execution |

#### ExecutionResult

```
output: string, error: string, exit_code: int, timed_out: bool, success: bool (property)
```

### 4.11 Credentials

#### Credential Store Integration

The server stores encrypted credentials (AES-256-GCM). SDKs interact via:

1. **Declaration** — Tools/agents declare credential names in their config
2. **Execution token** — Server mints a scoped token at workflow start
3. **Resolution** — Workers call `POST /api/credentials/resolve` with the token
4. **Injection** — SDK injects resolved values into tool execution context

#### Credential Isolation Modes

| Mode | Description |
|------|-------------|
| Isolated subprocess (default) | Tool runs in subprocess with credentials as env vars |
| In-process | Tool calls `get_credential(name)` directly |
| CLI injection | Credentials injected into CLI tool env |
| HTTP header injection | Server substitutes `${credential.NAME}` in headers |
| MCP credential injection | Passed to MCP server connection |
| Framework agent workers | Passed to extracted tool workers from framework agents |

#### CredentialFile

Declares a credential requirement:
- `env_var`: the logical name (e.g., `GITHUB_TOKEN`)
- `relative_path`: optional path relative to subprocess HOME (for file-based credentials like `KUBECONFIG`)
- `content`: optional static content (alternative to store lookup)

#### get_credential(name) → string

Resolves a single credential from the store. Uses the execution token from `__agentspan_ctx__`.

#### resolve_credentials(input_data, names) → map

Bulk resolution for external workers. Extracts execution token from task input.

#### Exception Hierarchy

```
CredentialNotFoundError — credential doesn't exist
CredentialAuthError     — token invalid/expired
CredentialRateLimitError — 120 calls/min exceeded
CredentialServiceError  — server error
```

### 4.12 Callbacks

#### CallbackHandler

Lifecycle hooks. Method names map to wire format positions:

| Method | Wire Position | When |
|--------|--------------|------|
| `on_agent_start(agent_name, prompt)` | `before_agent` | Agent begins execution |
| `on_agent_end(agent_name, result)` | `after_agent` | Agent completes |
| `on_model_start(agent_name, messages)` | `before_model` | LLM call begins |
| `on_model_end(agent_name, response)` | `after_model` | LLM call completes |
| `on_tool_start(agent_name, tool_name, args)` | `before_tool` | Tool invocation begins |
| `on_tool_end(agent_name, tool_name, result)` | `after_tool` | Tool invocation completes |

**Wire format:** Callbacks are serialized as `{"position": "<wire_position>", "taskName": "<agent_name>_<wire_position>"}`. The position values are `before_agent`, `after_agent`, `before_model`, `after_model`, `before_tool`, `after_tool` — NOT the method names.

Callbacks are registered as Conductor workers (same as tools). The server dispatches to them at the appropriate lifecycle points.

### 4.13 Extended Agent Types

#### UserProxyAgent

Human stand-in agent for multi-agent conversations:
- Modes: `ALWAYS` (always ask), `TERMINATE` (ask on termination), `NEVER` (auto-respond)
- Wraps HITL interaction as an agent in the team

#### GPTAssistantAgent

Wraps OpenAI Assistants API:
- Thread-based conversation management
- File search / code interpreter support
- Automatic tool mapping

### 4.14 Agent Discovery

#### discover_agents(path) → Agent[]

Scans a directory for agent definitions. Useful for agent repositories.

### 4.15 Tracing

#### is_tracing_enabled() → bool

Checks if OpenTelemetry is configured. SDKs should support optional OTel integration.

### 4.16 Exceptions

| Exception | Description |
|-----------|-------------|
| `AgentspanError` | Base exception |
| `AgentAPIError` | Server returned an error |
| `AgentNotFoundError` | Agent not found |
| `ConfigurationError` | Invalid agent configuration (missing model, conflicting settings) |

### 4.17 @agent Decorator

The `@agent` decorator is an alternative to `Agent()` for defining agents from functions. It attaches an `AgentDef` to the decorated function, which can then be used anywhere an `Agent` is expected:

```python
@agent(name="researcher", model="openai/gpt-4o", tools=[search])
def researcher(prompt: str) -> str:
    """Research assistant that finds information."""
    pass  # implementation handled by the runtime
```

The decorator accepts all the same parameters as the `Agent` constructor. Each SDK should provide an equivalent pattern (annotation, attribute, or builder).

---

## 5. Worker System

### 5.1 How Tools Become Workers

1. SDK encounters a `@tool` function during serialization
2. Generates a Conductor task definition (name, input schema, timeout, retry policy)
3. Registers a **worker function** that:
   a. Receives task input (JSON) from Conductor
   b. Deserializes input parameters
   c. Extracts `__agentspan_ctx__` for ToolContext
   d. Resolves credentials (if declared)
   e. Calls the user's function
   f. Serializes the return value to JSON
   g. Returns result to Conductor
4. Starts a **poll loop** (thread/goroutine/fiber) that:
   - Polls Conductor for tasks of this type
   - Executes the worker function
   - Reports success/failure back to Conductor

### 5.2 Worker Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Poll interval | 100ms | How often to check for tasks |
| Thread count | 1 | Concurrent executions per worker |
| Daemon mode | true | Kill on SDK shutdown |
| Timeout | 120s | Default task timeout |
| Retry count | 2 | Default retry count |
| Retry delay | 2s | Delay between retries |
| Retry policy | LINEAR_BACKOFF | Backoff strategy |

### 5.3 Framework Agent Compilation (REQUIRED)

**There is NO passthrough pattern.** Every framework agent MUST be compiled into a proper agentspan workflow — the same AgentConfig JSON → Conductor WorkflowDef compilation that native agents use. This is a hard requirement.

**Rationale:** The entire value of agentspan is durable, observable, distributed execution. A passthrough black-box task defeats this — you lose crash recovery at the tool level, visibility into intermediate steps, HITL at individual tool calls, and distributed worker execution. If a user wanted to run their framework agent as a black box, they wouldn't need agentspan.

#### What SDKs MUST do for framework agents

When `runtime.run(frameworkAgent, prompt)` is called with a framework agent (Vercel AI SDK, LangGraph, LangChain, OpenAI Agents, Google ADK), the SDK must:

1. **Detect** the framework via duck-typing
2. **Introspect** the framework agent to extract:
   - Model (LLM provider + model name)
   - Tools (function definitions with schemas)
   - Instructions/system prompt
   - Sub-agents (if multi-agent)
   - Configuration (temperature, max tokens, etc.)
3. **Map** the extracted components to agentspan primitives:
   - Framework agent → `AgentConfig` with model, instructions, tools
   - Framework tools → `ToolConfig` entries (toolType: 'worker' with local functions, or 'http'/'mcp' for server-side tools)
   - Framework sub-agents → nested `AgentConfig` entries
   - Framework orchestration → agentspan strategy (handoff, sequential, parallel, etc.)
4. **Serialize** to the standard AgentConfig JSON (identical wire format to native agents)
5. **Register** tool workers for extracted tool functions
6. **Execute** via the normal `POST /agent/start` → Conductor workflow → worker execution path

The resulting Conductor workflow must have **individual tasks per tool, per LLM call, per sub-agent** — NOT a single black-box task. The server's `AgentCompiler` handles the workflow compilation, but the SDK must produce an `AgentConfig` that represents the full agent structure.

#### Extraction paths per framework

| Framework | Model extraction | Tool extraction | Sub-agent extraction |
|-----------|-----------------|-----------------|---------------------|
| Vercel AI SDK | From `model` parameter | From `tools` object (Zod schemas + execute functions) | From nested `generateText` calls |
| LangGraph.js | From `ChatOpenAI`/model node | From `ToolNode.tools_by_name` | From StateGraph nodes |
| LangChain.js | From `ChatOpenAI` binding | From `tools` parameter or `AgentExecutor.tools` | From chain steps |
| OpenAI Agents SDK | From `agent.model` | From `agent.tools` (with schemas) | From `agent.handoffs` |
| Google ADK | From `agent.model` | From `agent.tools` (FunctionTool) | From `agent.subAgents` |

#### Drop-In Import Wrappers (Vercel AI SDK, LangGraph, LangChain)

Some frameworks hide model and tool references inside closures (e.g., `generateText` captures `model` in its options object, `createReactAgent` captures `llm` in a closure). JavaScript closures are opaque — unlike Python, there's no way to inspect captured variables.

The solution: **drop-in import wrappers** that intercept framework function calls at creation/invocation time, capture the model/tools/instructions BEFORE they disappear into closures, and store them as extractable properties.

**User's change: ONE import line per framework. Everything else unchanged.**

##### Vercel AI SDK

```typescript
// BEFORE (user's existing code):
import { generateText } from 'ai';

// AFTER (one import change):
import { generateText } from '@agentspan/sdk/vercel-ai';

// Everything else UNCHANGED:
const result = await generateText({
  model: openai('gpt-4o-mini'),
  tools: { weather: weatherTool },
  system: 'You are helpful.',
  prompt: 'What is the weather?',
});
// Now compiles to: LLM_CHAT_COMPLETE + SIMPLE per tool on Conductor
```

`@agentspan/sdk/vercel-ai` re-exports everything from `ai` but wraps `generateText` and `streamText`. The wrapper:
1. Intercepts the options object `{ model, tools, system, maxSteps, prompt }`
2. Extracts model (provider + model name from the AI SDK model object)
3. Extracts tools (Zod schemas + execute functions → `ToolConfig[]` with workers)
4. Extracts system prompt → `instructions`
5. Compiles to `AgentConfig` → sends to server → Conductor workflow
6. Returns the same result type the user expects

##### LangGraph

```typescript
// BEFORE:
import { createReactAgent } from '@langchain/langgraph/prebuilt';

// AFTER:
import { createReactAgent } from '@agentspan/sdk/langgraph';

// Everything else UNCHANGED:
const graph = createReactAgent({ llm: new ChatOpenAI({ model: 'gpt-4o-mini' }), tools: [search] });
const result = await graph.invoke({ messages: [new HumanMessage('Search for...')] });
```

The wrapper captures `llm` and `tools` at creation time (before they enter closures) and stores them as extractable properties on the returned graph object. When `runtime.run(graph, prompt)` is called, or when `graph.invoke()` is called, the extraction finds them.

For custom `StateGraph`, the wrapper intercepts `addNode()` to capture node functions and `compile()` to store the final graph structure.

##### LangChain

```typescript
// BEFORE:
import { AgentExecutor } from 'langchain/agents';

// AFTER:
import { AgentExecutor } from '@agentspan/sdk/langchain';

// Everything else UNCHANGED
```

The wrapper captures `agent` (with its LLM) and `tools` at `AgentExecutor` construction time.

##### OpenAI Agents & Google ADK: Zero Changes Required

These frameworks expose model, tools, and instructions as **public properties** on their Agent classes. No wrapper needed — the generic serializer extracts everything directly:

```typescript
// OpenAI — zero changes
import { Agent } from '@openai/agents';
const agent = new Agent({ name: 'test', model: 'gpt-4o', tools: [...] });
const result = await runtime.run(agent, 'Hello');  // model/tools extracted from public properties

// Google ADK — zero changes
import { LlmAgent } from '@google/adk';
const agent = new LlmAgent({ name: 'test', model: 'gemini-2.5-flash', tools: [...] });
const result = await runtime.run(agent, 'Hello');  // model/tools extracted from public properties
```

##### SDK Subpath Exports for Wrappers

```json
{
  "exports": {
    ".": "./dist/index.js",
    "./ai": "./dist/wrappers/ai.js",
    "./langgraph": "./dist/wrappers/langgraph.js",
    "./langchain": "./dist/wrappers/langchain.js",
    "./testing": "./dist/testing/index.js"
  }
}
```

##### What Each Wrapper Does

| Wrapper | Intercepts | Captures | Stores On |
|---------|-----------|----------|-----------|
| `@agentspan/sdk/vercel-ai` | `generateText`, `streamText` | model, tools, system, maxSteps | Options object → AgentConfig at call time |
| `@agentspan/sdk/langgraph` | `createReactAgent`, `StateGraph` | llm, tools at creation | Graph object properties |
| `@agentspan/sdk/langchain` | `AgentExecutor`, chain builders | agent.llm, tools at construction | Executor object properties |

#### Detection (duck-typing, no hard imports)

SDKs detect framework agents via property/method signatures without importing framework packages.

| Framework | Integration method | Detection |
|-----------|-------------------|-----------|
| Vercel AI SDK | Drop-in wrapper (`@agentspan/sdk/vercel-ai`) | N/A — intercepted at call site |
| LangGraph.js | Drop-in wrapper (`@agentspan/sdk/langgraph`) + duck-typing for wrapped graphs | Has `invoke()` + `_agentspan` metadata (set by wrapper) |
| LangChain.js | Drop-in wrapper (`@agentspan/sdk/langchain`) + duck-typing for wrapped executors | Has `invoke()` + `_agentspan` metadata (set by wrapper) |
| OpenAI Agents SDK | Direct extraction (zero changes) | Has `name` + `instructions` + `model` + `tools` + `handoffs` |
| Google ADK | Direct extraction (zero changes) | Has `model` + `instruction` + ADK-specific properties |

#### Summary: User Changes Required Per Framework

| Framework | User changes | What happens |
|-----------|-------------|-------------|
| **Vercel AI SDK** | Change 1 import: `from 'ai'` → `from '@agentspan/sdk/vercel-ai'` | `generateText` intercepted, compiled to workflow |
| **LangGraph** | Change 1 import: `from '@langchain/langgraph/prebuilt'` → `from '@agentspan/sdk/langgraph'` | `createReactAgent` captures llm/tools at creation |
| **LangChain** | Change 1 import: `from 'langchain/agents'` → `from '@agentspan/sdk/langchain'` | `AgentExecutor` captures agent/tools at construction |
| **OpenAI Agents** | **Zero changes** | Extracted from public properties |
| **Google ADK** | **Zero changes** | Extracted from public properties |

#### Framework-Specific Extraction: LangGraph

**With wrapper (`@agentspan/sdk/langgraph`):**

The wrapper intercepts `createReactAgent` and captures `llm` + `tools` at creation time — before they enter closures. These are stored as `_agentspan` metadata on the returned graph. When `runtime.run(graph, prompt)` is called, the SDK reads the metadata.

**Direct extraction (without wrapper — for graphs from `@langchain/langgraph` directly):**

The SDK attempts to extract from the compiled graph's public structure:
1. Finds tools from `graph.nodes.tools.bound.tools` (ToolNode)
2. Attempts to find model from node properties (may fail for closure-captured models)
3. If model can't be found, throws an error suggesting the wrapper import

**Full extraction (create_react_agent with wrapper):**

`createReactAgent({ llm, tools })` via the wrapper stores model + tools. The SDK:
1. Reads `_agentspan.model` and `_agentspan.tools` from the graph
2. Extracts system prompt from wrapper metadata
3. Produces `AgentConfig` with `model` + `tools[]` → compiles to `LLM_CHAT_COMPLETE` + `SIMPLE` tasks

**Graph-structure extraction (custom StateGraph):**

Custom `StateGraph` with explicit nodes and edges:
1. Each node function → becomes a `SIMPLE` Conductor task with its own worker
2. Simple edges → sequential task flow
3. Conditional edges → `SWITCH` tasks (see routing below)
4. LLM nodes (nodes that reference an LLM variable) → split into prep (SIMPLE) + `LLM_CHAT_COMPLETE` + finish (SIMPLE)
5. Subgraph nodes → recursively compiled as `SUB_WORKFLOW`

**Conditional routing in TypeScript:**

Python extracts router logic via bytecode inspection (`co_names`). TypeScript cannot do this — functions are opaque. Two approaches:

1. **Static analysis of return values:** If the conditional edge mapping is provided (e.g., `{ "escalate": "escalate_node", "respond": "respond_node" }`), the routing targets are known. The router function itself becomes a SIMPLE task worker that returns the route key. The server compiles this as a SWITCH: router worker → SWITCH on result → branch tasks.

2. **When routing can't be extracted:** The SDK throws an error with guidance:
   ```
   Error: Cannot extract conditional routing from StateGraph node 'classify'.
   Consider using createReactAgent() or express routing as an agentspan Agent
   with strategy='router'.
   ```

**LangGraph memory (MemorySaver/checkpointer):**

LangGraph's `MemorySaver` is framework-specific state persistence. When detected:
- Map to agentspan `ConversationMemory` if the checkpointer stores message history
- If the checkpointer does framework-specific state management that doesn't map to agentspan memory, throw an error with guidance to use agentspan's native memory system

**What MUST succeed (no errors allowed):**
- `createReactAgent({ llm, tools })` — always fully extractable
- `createReactAgent({ llm, tools, prompt })` — always fully extractable
- Simple `StateGraph` with function nodes + simple edges — always extractable
- `StateGraph` with conditional edges and explicit target mapping — extractable (router becomes SIMPLE worker)

**What MAY fail with a clear error:**
- `StateGraph` with `Send` API (dynamic fan-out) — complex; error with guidance
- Graphs with custom `channel_write`/`channel_read` — framework-internal; error with guidance

#### Framework-Specific Extraction: LangChain

**AgentExecutor extraction:**

`AgentExecutor` wraps an LLM agent + tools:
1. Extract model from `executor.agent` (typically `ChatOpenAI` or similar)
2. Extract tools from `executor.tools` — each has `.name`, `.description`, `.args_schema`
3. Extract system prompt from the agent's prompt template
4. Produces `AgentConfig` with `model` + `tools[]` → compiles to `LLM_CHAT_COMPLETE` + `SIMPLE` tasks

**RunnableSequence extraction (chains):**

A `RunnableSequence` is a pipeline of steps. Each step is a `Runnable`:
1. Each `RunnableLambda` (wraps a function) → becomes a `SIMPLE` Conductor task with a worker. The function is extractable as a property on the Runnable, and each step is its own task — this IS genuine decomposition, not a black box.
2. Each `ChatOpenAI` call → becomes a `LLM_CHAT_COMPLETE` task
3. Each `StructuredOutputParser` → becomes a post-processing SIMPLE task
4. The chain sequence → maps to agentspan `strategy: 'sequential'`

**What MUST succeed:**
- `AgentExecutor.from_agent_and_tools({ agent, tools })` — always fully extractable
- `createOpenAIFunctionsAgent` + `AgentExecutor` — always fully extractable
- Simple `RunnableSequence` of prompt → LLM → parser — always extractable

**What MAY fail with a clear error:**
- Custom `Runnable` subclasses with no extractable function — error with guidance
- Chains using `RunnablePassthrough` with complex merging — error with guidance

#### Framework-Specific Extraction: OpenAI Agents SDK

**Fully extractable via public properties — no special handling needed:**

The `Agent` class exposes everything as public properties:
- `.model` → `AgentConfig.model` (prefix with `openai/` if needed)
- `.instructions` → `AgentConfig.instructions`
- `.tools` → `AgentConfig.tools[]` (each tool has `.name`, `.description`, `.params_json_schema`, callable)
- `.handoffs` → `AgentConfig.agents[]` with `strategy: 'handoff'` (recursive extraction)
- `.output_type` → `AgentConfig.outputType`
- `.input_guardrails` / `.output_guardrails` → `AgentConfig.guardrails[]`
- `.model_settings` → `temperature`, `maxTokens`

The generic serializer walks these properties. The server's `OpenAINormalizer` maps the raw config to `AgentConfig`. **No framework-specific serializer needed.**

#### Framework-Specific Extraction: Google ADK

**Fully extractable via public properties — no special handling needed:**

The `LlmAgent` class exposes everything:
- `.model` → `AgentConfig.model` (prefix with `google_gemini/` if needed)
- `.instruction` → `AgentConfig.instructions`
- `.tools` → `AgentConfig.tools[]` (each `FunctionTool` has `.name`, `.description`, `.parameters`, `.execute`)
- `.subAgents` → `AgentConfig.agents[]` (recursive extraction)
- `.generateContentConfig` → temperature, maxTokens
- `.outputKey` → metadata

The generic serializer walks these properties. The server's `GoogleADKNormalizer` maps the raw config to `AgentConfig`. **No framework-specific serializer needed.**

#### Framework packages as optional dependencies

Framework packages are optional peer/dev dependencies. Only needed when running framework-specific examples. The core SDK works without them.

### 5.4 Credential Injection in Workers

When a tool declares credentials, the worker:
1. Extracts the execution token from `__agentspan_ctx__`
2. Calls `POST /api/credentials/resolve` with the token + credential names
3. Injects resolved values either:
   a. As environment variables in a subprocess (isolated mode)
   b. As parameters to the tool function (in-process mode)

### 5.5 External Workers (By Reference)

External tools/guardrails/agents have no local worker. The SDK:
1. Emits the task name in AgentConfig
2. Does NOT register a local worker
3. Trusts that a remote worker (possibly in another language, another machine) will pick up the task

This is the core mechanism for distributed agent systems.

---

## 6. Streaming Implementation

### 6.1 SSE Client Requirements

Every SDK must implement an SSE client that:
1. Connects to `GET /agent/stream/{workflowId}` with `Accept: text/event-stream`
2. Parses SSE wire format (event, id, data fields)
3. Handles heartbeat comments (`:` prefix lines)
4. Reconnects on connection drop with `Last-Event-ID` header
5. Detects SSE unavailability (only heartbeats for 15s → fallback to polling)
6. Yields parsed AgentEvent objects

### 6.2 SSE Wire Format Parsing

```
event: <event_type>    → maps to AgentEvent.type
id: <monotonic_int>    → used for reconnection
data: <json_string>    → parsed to AgentEvent fields
                       → blank line = end of event
:<comment>             → heartbeat (ignore)
```

### 6.3 Polling Fallback

If SSE is unavailable:
1. Poll `GET /agent/{id}/status` at regular intervals (e.g., 500ms)
2. Detect state changes and emit synthetic events
3. Stop when `is_complete` is true

---

## 7. Sync + Async Dual Execution Model

Every execution API must have both sync and async variants. The internal implementation should be async-native, with sync wrappers that block.

### 7.1 Per-Language Async Model

| Language | Async Primitive | Sync Wrapper |
|----------|----------------|--------------|
| Python | `asyncio` / `async def` | `asyncio.run()` in thread |
| TypeScript | `Promise` / `async function` | N/A (inherently async) |
| Go | goroutines + channels | Blocking by default, goroutines for async |
| Java | `CompletableFuture` / virtual threads (21+) | `.get()` / `.join()` |
| Kotlin | `suspend fun` / coroutines | `runBlocking { }` |
| C# | `Task<T>` / `async Task` | `.GetAwaiter().GetResult()` |
| Ruby | `Async` / `Fiber` (async-ruby) | Blocking by default |

### 7.2 Internal Components That Need Async

| Component | Why Async |
|-----------|-----------|
| HTTP client | Non-blocking API calls |
| Worker poll loop | Concurrent task polling |
| SSE client | Long-lived streaming connection |
| Credential resolution | Network call during tool execution |

---

## 8. Kitchen Sink Specification

### 8.1 Scenario: Content Publishing Platform

A single mega-workflow that processes an article request through a complete publishing pipeline, exercising every SDK feature.

### 8.2 Stage Breakdown

#### Stage 1 — Intake & Classification
**Features:** Router strategy, structured output, PromptTemplate

- Router agent classifies request into category (tech, business, creative)
- Uses `PromptTemplate` for classification prompt (server-managed)
- Returns structured output: `{ category: string, priority: int, metadata: map }`

#### Stage 2 — Research Team
**Features:** Parallel strategy, scatter_gather, native tools, HTTP tools, MCP tools, credentials, ToolContext injection, external tools

- Parallel agents: web researcher (HTTP tools + credentials), data analyst (native `@tool`), fact checker (MCP tools)
- `scatter_gather()` collects results
- Native tools demonstrate `ToolContext` injection (session_id, workflow_id)
- HTTP tool hits an API with credential-based auth headers
- MCP tool connects to an MCP server
- External tool references a remote research worker (by-reference, no local implementation)

#### Stage 3 — Writing Pipeline
**Features:** Sequential strategy, `>>` chaining, ConversationMemory, SemanticMemory, CallbackHandler

- `researcher >> writer >> editor` pipeline
- ConversationMemory carries context through the chain
- SemanticMemory recalls relevant past articles
- CallbackHandler logs lifecycle events

#### Stage 4 — Review & Safety
**Features:** All guardrail types (regex, LLM, custom, external), all OnFail modes, tool guardrails

- Input guardrail: RegexGuardrail blocks PII (on_fail=RETRY)
- Output guardrail: LLMGuardrail checks bias (on_fail=FIX)
- Custom `@guardrail` validates facts (on_fail=HUMAN)
- External guardrail: remote compliance checker (by-reference, on_fail=RAISE)
- Tool guardrail: validates tool inputs before execution

#### Stage 5 — Editorial Approval
**Features:** HITL (all modes), UserProxyAgent, human_tool, streaming + HITL

- `approval_required=True` on publish tool → durable pause
- `human_tool()` for inline editorial questions
- `handle.respond()` with feedback for revision loop
- UserProxyAgent participates as editorial reviewer
- Streaming events show real-time progress + pause notification

#### Stage 6 — Translation & Discussion
**Features:** Round-robin, swarm, manual, random strategies, OnTextMention, agent_introductions, allowed_transitions

- Round-robin debate between translators on tone/style
- Swarm with `OnTextMention` for automatic handoff between language specialists
- Manual selection for human to pick final translator
- Random strategy for brainstorming alternative titles
- `agent_introductions` for agents to announce their role
- `allowed_transitions` restricts delegation paths

#### Stage 7 — Publishing Pipeline
**Features:** Handoff strategy, OnToolResult, OnCondition, external agents, termination conditions (composable), gate conditions

- Handoff with `OnToolResult` and `OnCondition`
- External agent: formatting service (by-reference SUB_WORKFLOW)
- Composable termination: `TextMentionTermination("PUBLISHED") | (MaxMessageTermination(50) & TokenUsageTermination(100000))`
- Gate condition on sequential pipeline stage

#### Stage 8 — Analytics & Reporting
**Features:** All code executors, all media tools, RAG tools, token tracking, GPTAssistantAgent

- `LocalCodeExecutor` runs analysis script
- `DockerCodeExecutor` runs sandboxed processing
- `JupyterCodeExecutor` generates visualizations
- `ServerlessCodeExecutor` runs cloud function
- `image_tool()`, `audio_tool()`, `video_tool()`, `pdf_tool()` for media
- `search_tool()`, `index_tool()` for RAG
- Token usage tracking across all stages
- `GPTAssistantAgent` wraps OpenAI assistant for research

#### Stage 9 — Deployment & Execution Modes
**Features:** deploy, serve, plan, run/run_async, start/start_async, stream/stream_async

- `deploy()` registers the workflow
- `plan()` compile-only dry-run preview
- `run()` synchronous execution
- `run_async()` asynchronous execution
- `start()` fire-and-forget + polling
- `stream()` / `stream_async()` real-time streaming

### 8.3 Cross-Cutting Concerns

Exercised throughout the workflow:

- **All credential modes:** isolated subprocess, in-process `get_credential()`, CLI injection, HTTP header injection, MCP credential injection, framework agent workers, external worker credentials
- **CliConfig:** CLI tool allowlisting for git/gh commands
- **CodeExecutionConfig:** Sandbox settings for code execution
- **Extended thinking:** `thinking_budget_tokens` on analysis agent
- **Include contents:** File contents injected into agent prompt
- **Planner mode:** Planning agent for research strategy
- **Metadata:** Custom metadata passed through workflow
- **Context condensation:** Auto-condense when context window fills

### 8.4 Testing Section

The kitchen sink includes a comprehensive test suite:

| Test Type | Description |
|-----------|-------------|
| `mock_run()` | Execute without server for unit testing (in `testing` subpackage) |
| `expect()` fluent API | `expect(result).completed().output_contains("article")` |
| `assert_*()` functions | `assert_tool_used("search")`, `assert_guardrail_passed("pii_check")` |
| `record()` / `replay()` | Capture execution for deterministic replay |
| `validate_strategy()` | Verify strategy constraints were respected |
| `CorrectnessEval` | LLM judge evaluates output quality against rubrics |

### 8.5 Expected Behavior & Judge Rubrics

Each stage has defined:
1. **Structural assertions** — specific tools called, guardrails triggered, events emitted
2. **Behavioral assertions** — output contains expected content, correct status/finish_reason
3. **Judge rubrics** — semantic evaluation criteria for LLM judge:
   - Research quality (sources cited, facts checked)
   - Writing quality (coherent, on-topic)
   - Safety (PII removed, bias checked)
   - Completeness (all pipeline stages executed)

### 8.6 Acceptance Criteria

A new SDK passes the kitchen sink if:
1. Produces identical AgentConfig JSON for the same agent tree
2. Workers successfully execute all tool/guardrail/callback tasks
3. SSE streaming yields the same event sequence
4. HITL interactions complete correctly
5. Final AgentResult matches expected output structure
6. All test assertions pass
7. LLM judge scores ≥ threshold on all rubrics

---

## 9. Validation Framework

### 9.1 Requirements

Every SDK must include a validation framework that mirrors the Python implementation:

| Component | Description |
|-----------|-------------|
| Validation runner | Concurrent executor, runs examples against multiple models |
| TOML config | Configuration for runs (model, group, timeout, etc.) |
| Example groups | SMOKE_TEST, PASSING, SLOW, HITL, per-framework (langgraph, langchain, vercel_ai, openai, google_adk) |
| LLM judge | Cross-run semantic evaluation with rubrics |
| HTML report | Interactive dashboard with score heatmap, filters |
| Resume/retry | Resume failed runs, retry specific examples |

### 9.2 Native SDK Execution (Validation Only)

For validation purposes, each SDK must support running examples using the framework's **native SDK** to compare outputs:

| Framework | Native SDK | Purpose |
|-----------|-----------|---------|
| OpenAI Agents | `openai-agents` (Python), equivalent per language | Compare agentspan-compiled vs native execution |
| Google ADK | `google-adk` (Python), equivalent per language | Same |
| LangChain | `langchain` per language | Same |
| LangGraph | `langgraph` per language | Same |
| Vercel AI SDK | `ai` (TypeScript) | Compare agentspan-compiled vs native execution |

This is **validation-only** — not a runtime dependency. The validation runner:
1. Runs the example via agentspan compilation (normal path)
2. Runs the same example via the native SDK (bypass path)
3. LLM judge compares both outputs for semantic equivalence
4. Reports divergences

### 9.3 Judge Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `judge_model` | gpt-4o-mini | LLM model for judging |
| `max_output_chars` | 3000 | Truncate outputs before judging |
| `max_tokens` | 300 | Max tokens for judge response |
| `max_calls` | 0 (unlimited) | Budget cap |
| `rate_limit` | 0.5s | Delay between judge calls |

---

## 10. Per-Language Translation Guide Template

Each language doc follows this structure:

### 10.1 Project Setup
- Package manager, build toolchain, directory layout
- Dependencies: HTTP client, SSE client, JSON serializer, Conductor client (if available)

### 10.2 Type System Mapping

| Python | TypeScript | Go | Java (record) | Java (POJO) | Kotlin | C# | Ruby |
|--------|-----------|-----|---------------|-------------|--------|-----|------|
| `dataclass` | `interface`/`class` | `struct` | `record` | Class + getters/Lombok | `data class` | `record` | `Struct`/`Data` |
| `enum(str, Enum)` | `enum`/union type | `const` iota | `enum` | `enum` | `enum class`/`sealed class` | `enum` | Symbol/constants |
| `Optional[T]` | `T \| null` | `*T` | `Optional<T>` | `@Nullable` | `T?` | `T?` | nilable |
| `list[T]` | `T[]` | `[]T` | `List<T>` | `List<T>` | `List<T>` | `List<T>` | `Array` |
| `dict[K, V]` | `Record<K, V>` | `map[K]V` | `Map<K, V>` | `Map<K, V>` | `Map<K, V>` | `Dictionary<K, V>` | `Hash` |
| `Callable` | `Function` | `func` | `Function<>` | interface | lambda/`() -> T` | `Func<>`/`Action<>` | `Proc`/`lambda` |
| Pydantic `BaseModel` | zod/class-validator | struct tags + validation | Jackson annotations | Jackson annotations | kotlinx.serialization | System.Text.Json | dry-schema |
| `Union[A, B]` | `A \| B` | interface | sealed interface | — | sealed class | OneOf pattern | duck typing |

### 10.3 Decorator/Annotation Pattern

| Pattern | TypeScript | Go | Java | Kotlin | C# | Ruby |
|---------|-----------|-----|------|--------|-----|------|
| `@agent` | Decorator (experimental) or builder | Functional options | `@Agent` annotation | DSL builder | `[Agent]` attribute | DSL block |
| `@tool` | `@Tool()` decorator or `tool()` fn | `Tool()` functional option | `@Tool` annotation | `tool { }` DSL | `[Tool]` attribute | `tool` method |
| `@guardrail` | `@Guardrail()` or `guardrail()` fn | `Guardrail()` functional option | `@Guardrail` annotation | `guardrail { }` DSL | `[Guardrail]` attribute | `guardrail` method |
| `>>` operator | `.pipe()` method | `Pipeline()` builder | `.then()` method | `then` infix | `>>` operator overload | `>>` operator |
| `&` / `\|` operators | `.and()` / `.or()` | `And()` / `Or()` | `.and()` / `.or()` | `and` / `or` infix | `&` / `\|` operator | `&` / `\|` operator |

### 10.4 Async Model

(See Section 7.1)

### 10.5 Worker Implementation
- Thread/goroutine/fiber model for Conductor task polling
- JSON deserialization of task inputs
- Credential resolution during task execution
- Result serialization and reporting

### 10.6 SSE Client
- HTTP streaming library
- Line-by-line SSE parsing
- Reconnection with Last-Event-ID
- Heartbeat handling

### 10.7 Error Handling
- Exception/error hierarchy mapping
- Guardrail failure propagation
- Timeout handling patterns

### 10.8 Testing Framework
- `mock_run()` equivalent
- `expect()` fluent API in language idioms
- Assertion functions
- Record/replay
- Validation runner + judge integration

### 10.9 Kitchen Sink Translation
- Complete working implementation
- Behavioral parity verification against Python version

---

## 11. Feature Traceability Matrix

Every feature must be traceable from concept → Python reference → wire format → server behavior → acceptance test.

| # | Feature | Python Module | Wire Format Key | Server Handler | Kitchen Sink Stage |
|---|---------|--------------|-----------------|---------------|-------------------|
| 1 | Agent definition | `agent.py:Agent` | `agentConfig.name/model/instructions` | AgentCompiler | All |
| 2 | Strategy: handoff | `agent.py:Strategy.HANDOFF` | `agentConfig.strategy="handoff"` | MultiAgentCompiler | Stage 7 |
| 3 | Strategy: sequential | `agent.py:Strategy.SEQUENTIAL` | `agentConfig.strategy="sequential"` | MultiAgentCompiler | Stage 3 |
| 4 | Strategy: parallel | `agent.py:Strategy.PARALLEL` | `agentConfig.strategy="parallel"` | MultiAgentCompiler (FORK_JOIN) | Stage 2 |
| 5 | Strategy: router | `agent.py:Strategy.ROUTER` | `agentConfig.strategy="router"` | MultiAgentCompiler (SWITCH) | Stage 1 |
| 6 | Strategy: round_robin | `agent.py:Strategy.ROUND_ROBIN` | `agentConfig.strategy="round_robin"` | MultiAgentCompiler | Stage 6 |
| 7 | Strategy: random | `agent.py:Strategy.RANDOM` | `agentConfig.strategy="random"` | MultiAgentCompiler | Stage 6 |
| 8 | Strategy: swarm | `agent.py:Strategy.SWARM` | `agentConfig.strategy="swarm"` | MultiAgentCompiler | Stage 6 |
| 9 | Strategy: manual | `agent.py:Strategy.MANUAL` | `agentConfig.strategy="manual"` | MultiAgentCompiler | Stage 6 |
| 10 | Native tool (@tool) | `tool.py:tool` | `tools[].toolType="worker"` | ToolCompiler → SIMPLE | Stage 2 |
| 11 | HTTP tool | `tool.py:http_tool` | `tools[].toolType="http"` | ToolCompiler → HTTP | Stage 2 |
| 12 | MCP tool | `tool.py:mcp_tool` | `tools[].toolType="mcp"` | ToolCompiler → CALL_MCP_TOOL | Stage 2 |
| 13 | Agent tool | `tool.py:agent_tool` | `tools[].toolType="agent_tool"` | ToolCompiler → SUB_WORKFLOW | Stage 8 |
| 14 | Human tool | `tool.py:human_tool` | `tools[].toolType="human"` | ToolCompiler → HUMAN | Stage 5 |
| 15 | Image/audio/video/pdf tool | `tool.py:image_tool` etc | `tools[].toolType="generate_*"` | ToolCompiler → GENERATE_* | Stage 8 |
| 16 | Search/index tool | `tool.py:search_tool` | `tools[].toolType="rag_search\|rag_index"` | ToolCompiler → LLM_*_INDEX | Stage 8 |
| 17 | Tool approval | `tool.py:approval_required` | `tools[].approvalRequired=true` | HUMAN task wrapper | Stage 5 |
| 18 | Tool context | `tool.py:ToolContext` | `__agentspan_ctx__` in task input | Injected by server | Stage 2 |
| 19 | Tool credentials | `tool.py:credentials` | `tools[].config.credentials` | ExecutionTokenService | Stage 2 |
| 20 | Tool guardrails | `tool.py:guardrails` | `tools[].guardrails` | GuardrailCompiler | Stage 4 |
| 21 | External tool | `tool.py:external=True` | `tools[].toolType="worker"` (no worker) | SIMPLE (remote) | Stage 2 |
| 22 | Regex guardrail | `guardrail.py:RegexGuardrail` | `guardrails[].guardrailType="regex"` | GuardrailCompiler → INLINE | Stage 4 |
| 23 | LLM guardrail | `guardrail.py:LLMGuardrail` | `guardrails[].guardrailType="llm"` | GuardrailCompiler → LLM_CHAT | Stage 4 |
| 24 | Custom guardrail | `guardrail.py:@guardrail` | `guardrails[].guardrailType="custom"` | GuardrailCompiler → SIMPLE | Stage 4 |
| 25 | External guardrail | `guardrail.py:external=True` | `guardrails[].guardrailType="external"` | SIMPLE (remote) | Stage 4 |
| 26 | OnFail: retry | `guardrail.py:OnFail.RETRY` | `guardrails[].onFail="retry"` | DO_WHILE loop | Stage 4 |
| 27 | OnFail: raise | `guardrail.py:OnFail.RAISE` | `guardrails[].onFail="raise"` | Workflow FAILED | Stage 4 |
| 28 | OnFail: fix | `guardrail.py:OnFail.FIX` | `guardrails[].onFail="fix"` | Use fixed_output | Stage 4 |
| 29 | OnFail: human | `guardrail.py:OnFail.HUMAN` | `guardrails[].onFail="human"` | HUMAN task | Stage 4 |
| 30 | Structured output | `agent.py:output_type` | `agentConfig.outputType` | JSON Schema validation | Stage 1 |
| 31 | ConversationMemory | `memory.py` | `agentConfig.memory` | Message history | Stage 3 |
| 32 | SemanticMemory | `semantic_memory.py` | SDK-side only | SDK-side retrieval | Stage 3 |
| 33 | Termination (composable) | `termination.py` | `agentConfig.termination` | Server-side eval | Stage 7 |
| 34 | Handoff: OnToolResult | `handoff.py:OnToolResult` | `handoffs[].type="on_tool_result"` | SWITCH task | Stage 7 |
| 35 | Handoff: OnTextMention | `handoff.py:OnTextMention` | `handoffs[].type="on_text_mention"` | SWITCH task | Stage 6 |
| 36 | Handoff: OnCondition | `handoff.py:OnCondition` | `handoffs[].type="on_condition"` | SIMPLE worker | Stage 7 |
| 37 | Allowed transitions | `agent.py:allowed_transitions` | `agentConfig.allowedTransitions` | Server-side enforcement | Stage 6 |
| 38 | Agent introductions | `agent.py:introduction` | `agentConfig.introduction` | Prepended to context | Stage 6 |
| 39 | Agent chaining (>>) | `agent.py:__rshift__` | Sequential strategy | MultiAgentCompiler | Stage 3 |
| 40 | HITL: approval gate | `result.py:AgentHandle.approve` | `POST /respond {approved:true}` | AgentHumanTask | Stage 5 |
| 41 | HITL: rejection | `result.py:AgentHandle.reject` | `POST /respond {approved:false}` | AgentHumanTask | Stage 5 |
| 42 | HITL: feedback | `result.py:AgentHandle.send` | `POST /respond {message:...}` | AgentHumanTask | Stage 5 |
| 43 | Streaming (SSE) | `result.py:AgentStream` | `GET /stream/{id}` | AgentStreamRegistry | All |
| 44 | Async streaming | `result.py:AsyncAgentStream` | Same SSE endpoint | Same | Stage 9 |
| 45 | Polling fallback | `runtime.py` | `GET /{id}/status` | AgentController | Stage 9 |
| 46 | Sync execution | `run.py:run` | POST /start + poll | AgentService | Stage 9 |
| 47 | Async execution | `run.py:run_async` | Same | Same | Stage 9 |
| 48 | Fire-and-forget | `run.py:start` | POST /start (no poll) | AgentService | Stage 9 |
| 49 | Deploy | `run.py:deploy` | POST /deploy | AgentService | Stage 9 |
| 50 | Serve | `run.py:serve` | Starts worker server | N/A | Stage 9 |
| 51 | Plan (dry run) | `run.py:plan` | POST /compile | AgentService | Stage 9 |
| 52 | Credentials: isolated | `credentials/isolator.py` | `__agentspan_ctx__` | CredentialResolutionService | Stage 2 |
| 53 | Credentials: in-process | `credentials/accessor.py` | `POST /credentials/resolve` | CredentialResolutionService | Cross-cutting |
| 54 | Credentials: CLI | `credentials/cli_map.py` | Env var injection | CredentialResolutionService | Cross-cutting |
| 55 | Credentials: HTTP header | `tool.py:http_tool` | `${credential.NAME}` substitution | Server-side | Cross-cutting |
| 56 | Credentials: MCP | `tool.py:mcp_tool` | MCP connection config | Server-side | Cross-cutting |
| 57 | Credentials: framework | `frameworks/` | Framework-specific | Per-framework | Cross-cutting |
| 58 | Code: local | `code_executor.py:Local` | `agentConfig.codeExecution` | Server-side | Stage 8 |
| 59 | Code: Docker | `code_executor.py:Docker` | Same | Server-side | Stage 8 |
| 60 | Code: Jupyter | `code_executor.py:Jupyter` | Same | Server-side | Stage 8 |
| 61 | Code: serverless | `code_executor.py:Serverless` | Same | Server-side | Stage 8 |
| 62 | Callbacks | `callback.py:CallbackHandler` | `agentConfig.callbacks` | Worker dispatch | Stage 3 |
| 63 | PromptTemplate | `agent.py:PromptTemplate` | `instructions.type="prompt_template"` | Server-side lookup | Stage 1 |
| 64 | Token tracking | `result.py:TokenUsage` | Status response | LLM_CHAT_COMPLETE | All |
| 65 | UserProxyAgent | `ext.py:UserProxyAgent` | AgentConfig + HUMAN | Hybrid | Stage 5 |
| 66 | GPTAssistantAgent | `ext.py:GPTAssistantAgent` | AgentConfig + threads | Hybrid | Stage 8 |
| 67 | Extended thinking | `agent.py:thinking_budget_tokens` | `agentConfig.thinkingConfig` | LLM param | Cross-cutting |
| 68 | Include contents | `agent.py:include_contents` | `agentConfig.includeContents` | Prompt injection | Cross-cutting |
| 69 | Planner mode | `agent.py:planner` | `agentConfig.planner=true` | Server-side | Cross-cutting |
| 70 | Required tools | `agent.py:required_tools` | `agentConfig.requiredTools` | LLM param | Cross-cutting |
| 71 | Gate conditions | `gate.py` | `agentConfig.gate` | SWITCH task | Stage 7 |
| 72 | CLI config | `cli_config.py:CliConfig` | `agentConfig.cliConfig` | Server-side | Cross-cutting |
| 73 | Context condensation | `runtime.py` | SSE event | Server-side | Cross-cutting |
| 74 | Agent discovery | `discovery.py` | N/A (SDK-side) | N/A | Stage 9 |
| 75 | OTel tracing | `tracing.py` | N/A (SDK-side) | N/A | Cross-cutting |
| 76 | scatter_gather | `agent.py:scatter_gather` | Parallel + collect | MultiAgentCompiler | Stage 2 |
| 77 | stop_when | `agent.py:stop_when` | `agentConfig.stopWhen.taskName` | Worker dispatch | Cross-cutting |
| 78 | Testing: mock_run | `testing/mock.py` | N/A | N/A | Testing |
| 79 | Testing: expect | `testing/expect.py` | N/A | N/A | Testing |
| 80 | Testing: assertions | `testing/assertions.py` | N/A | N/A | Testing |
| 81 | Testing: record/replay | `testing/recording.py` | N/A | N/A | Testing |
| 82 | Testing: strategy validators | `testing/strategy_validators.py` | N/A | N/A | Testing |
| 83 | Testing: eval runner | `testing/eval_runner.py` | N/A | N/A | Testing |
| 84 | Validation: runner | `validation/` | N/A | N/A | Validation |
| 85 | Validation: judge | `validation/` | N/A | N/A | Validation |
| 86 | Validation: native execution | `validation/` | N/A | N/A | Validation |
| 87 | Validation: HTML report | `validation/` | N/A | N/A | Validation |
| 88 | External agent | `agent.py:external=True` | `agentConfig.external=true` | SUB_WORKFLOW (remote) | Stage 7 |
| 89 | API tool (auto-discovery) | `tool.py:api_tool` | `tools[].toolType="api"` | LIST_API_TOOLS → HTTP | Stage 2 |

---

## 12. Implementation Order

Recommended order for implementing a new SDK:

1. **Configuration** — env vars, AgentConfig
2. **HTTP client** — all REST endpoints
3. **Agent + Tool types** — core data model
4. **Serialization** — AgentConfig JSON generation
5. **Worker system** — Conductor task polling + execution
6. **Runtime** — run(), start(), deploy() via HTTP
7. **SSE streaming** — stream(), event parsing
8. **Credentials** — execution token, resolve, injection
9. **Guardrails** — all types + OnFail modes
10. **Memory** — ConversationMemory, SemanticMemory
11. **Termination + Handoffs** — composable conditions
12. **Code execution** — all executor types
13. **Extended types** — UserProxyAgent, GPTAssistantAgent
14. **Callbacks** — lifecycle hooks
15. **Framework integration** — detection, extraction, compilation to AgentConfig (TypeScript: Vercel AI SDK; Python: LangGraph, LangChain)
16. **Testing framework** — mock, expect, assertions, record/replay
17. **Validation framework** — runner, judge, native execution, reports
18. **Kitchen sink** — full acceptance test
19. **Examples** — all Python examples ported (see §12.1)

### 12.1 Example Parity Requirement

Every SDK must port **all** Python examples to the target language. The Python SDK's examples directory is the reference — each example must have an equivalent in the new SDK, translated to idiomatic target-language patterns.

#### Native Agentspan Examples (97 examples)

These cover every feature of the native SDK. Each new SDK must implement all of them:

| # | Example | Features Covered |
|---|---------|-----------------|
| 01 | `basic_agent` | Agent definition, model, instructions, run() |
| 02 | `tools` | @tool decorator, input schemas |
| 02a | `simple_tools` | Single-step tool usage |
| 02b | `multi_step_tools` | Multi-step tool chains |
| 03 | `structured_output` | output_type, Pydantic/Zod schemas |
| 04 | `http_and_mcp_tools` | httpTool, mcpTool |
| 04 | `mcp_weather` | MCP tool with real server |
| 05 | `handoffs` | Strategy.HANDOFF, sub-agents |
| 06 | `sequential_pipeline` | Strategy.SEQUENTIAL, >> / .pipe() |
| 07 | `parallel_agents` | Strategy.PARALLEL |
| 08 | `router_agent` | Strategy.ROUTER |
| 09 | `human_in_the_loop` | approval_required, handle.approve() |
| 09b | `hitl_with_feedback` | handle.send(), handle.reject() |
| 09c | `hitl_streaming` | stream + HITL combined |
| 09d | `human_tool` | humanTool() |
| 10 | `guardrails` | Custom @guardrail functions |
| 11 | `streaming` | runtime.stream(), event iteration |
| 12 | `long_running` | Timeout, polling |
| 13 | `hierarchical_agents` | Nested multi-agent teams |
| 14 | `existing_workers` | External workers (by reference) |
| 15 | `agent_discussion` | Multi-agent conversation |
| 16 | `credentials_isolated_tool` | Isolated credential mode |
| 16 | `random_strategy` | Strategy.RANDOM |
| 16b | `credentials_non_isolated` | In-process getCredential() |
| 16c | `credentials_cli_tools` | CLI credential injection |
| 16d | `credentials_gh_cli` | GitHub CLI with credentials |
| 16e | `credentials_http_tool` | HTTP header ${CREDENTIAL} substitution |
| 16f | `credentials_mcp_tool` | MCP tool credentials |
| 16g | `credentials_framework_agent` | Framework agent credential injection |
| 16h | `credentials_external_worker` | External worker credentials |
| 16i | `credentials_langchain` | LangChain agent credential injection |
| 16j | `credentials_openai_sdk` | OpenAI SDK agent credential injection |
| 16k | `credentials_google_adk` | Google ADK agent credential injection |
| 17 | `swarm_orchestration` | Strategy.SWARM |
| 18 | `manual_selection` | Strategy.MANUAL |
| 19 | `composable_termination` | TextMention \| (MaxMessage & TokenUsage) |
| 20 | `constrained_transitions` | allowedTransitions |
| 21 | `regex_guardrails` | RegexGuardrail |
| 22 | `llm_guardrails` | LLMGuardrail |
| 23 | `token_tracking` | TokenUsage in result |
| 24 | `code_execution` | CodeExecutionConfig |
| 25 | `semantic_memory` | SemanticMemory + MemoryStore |
| 26 | `opentelemetry_tracing` | OTel integration |
| 27 | `user_proxy_agent` | UserProxyAgent |
| 28 | `gpt_assistant_agent` | GPTAssistantAgent |
| 29 | `agent_introductions` | introduction field |
| 30 | `multimodal_agent` | Media tools (image, audio, video, pdf) |
| 31 | `tool_guardrails` | Guardrails on tool input |
| 32 | `human_guardrail` | onFail=HUMAN |
| 33 | `external_workers` | External tools + agents |
| 33 | `single_turn_tool` | Single-turn tool execution |
| 34 | `prompt_templates` | PromptTemplate with variables |
| 35 | `standalone_guardrails` | Guardrails without agent |
| 36 | `simple_agent_guardrails` | Basic agent-level guardrails |
| 37 | `fix_guardrail` | onFail=FIX |
| 38 | `tech_trends` | Real-world research agent |
| 39 | `local_code_execution` | LocalCodeExecutor |
| 39a | `docker_code_execution` | DockerCodeExecutor |
| 39b | `jupyter_code_execution` | JupyterCodeExecutor |
| 39c | `serverless_code_execution` | ServerlessCodeExecutor |
| 40 | `media_generation_agent` | Image/audio/video/pdf tools |
| 41 | `sequential_pipeline_tools` | Sequential with shared tools |
| 42 | `security_testing` | Security-focused agent |
| 43 | `data_security_pipeline` | Multi-stage security pipeline |
| 44 | `safety_guardrails` | Comprehensive safety guardrails |
| 45 | `agent_tool` | agentTool() sub-agent as tool |
| 46 | `transfer_control` | Handoff conditions |
| 47 | `callbacks` | CallbackHandler lifecycle hooks |
| 48 | `planner` | planner=True mode |
| 49 | `include_contents` | includeContents="default" |
| 50 | `thinking_config` | thinkingBudgetTokens |
| 51 | `shared_state` | ToolContext.state mutations |
| 52 | `nested_strategies` | Mixed strategies (router→parallel→sequential) |
| 53 | `agent_lifecycle_callbacks` | All 6 callback positions |
| 54 | `software_bug_assistant` | Real-world debugging agent |
| 55 | `ml_engineering` | ML pipeline agent |
| 56 | `rag_agent` | searchTool + indexTool |
| 57 | `plan_dry_run` | runtime.plan() |
| 58 | `scatter_gather` | scatterGather() helper |
| 59 | `coding_agent` | Code generation + execution |
| 60 | `github_coding_agent` | GitHub integration |
| 60a | `github_coding_agent_simple` | Simplified GitHub agent |
| 61 | `github_coding_agent_chained` | Chained GitHub agents |
| 62 | `cli_tool_guardrails` | CliConfig + guardrails |
| 63 | `deploy` | runtime.deploy() |
| 63b | `serve` | runtime.serve() |
| 63c | `run_by_name` | Run deployed agent by name |
| 63d | `serve_from_package` | Serve agents from package |
| 63e | `run_monitoring` | Execution monitoring |
| 64 | `swarm_with_tools` | Swarm strategy + tool usage |
| 65 | `parallel_with_tools` | Parallel strategy + tools |
| 66 | `handoff_to_parallel` | Handoff → parallel sub-team |
| 67 | `router_to_sequential` | Router → sequential pipeline |
| 68 | `context_condensation` | Long conversations, context management |
| 70 | `ce_support_agent` | Customer engineering agent |
| 71 | `api_tool` | apiTool() OpenAPI auto-discovery |
| 90 | `guardrail_e2e_tests` | End-to-end guardrail testing |

#### Framework Examples

Each framework integration must have equivalent examples ported from Python. These demonstrate running native framework agents on agentspan's durable runtime.

**LangGraph Examples (44 examples)**

| # | Example | Features Covered |
|---|---------|-----------------|
| 01 | `hello_world` | Basic create_react_agent compiled to agentspan |
| 02 | `react_with_tools` | ReAct agent with tool calling |
| 03 | `memory` | Checkpointed memory |
| 04 | `simple_stategraph` | Custom StateGraph |
| 05 | `tool_node` | ToolNode extraction |
| 06 | `conditional_routing` | Conditional edges |
| 07 | `system_prompt` | System prompt injection |
| 08 | `structured_output` | Typed output |
| 09-14 | Domain agents | Math, research, customer support, code, multi-turn, QA |
| 15-20 | Advanced patterns | Data pipeline, parallel branches, error recovery, tools_condition, document analysis, planner |
| 21-27 | Complex patterns | Subgraph, HITL, retry, map-reduce, supervisor, handoff, persistent memory |
| 28-35 | Streaming & memory | Streaming tokens, tool categories, code interpreter, classify+route, reflection, output validator, RAG, conversation manager |
| 36-40 | Multi-agent | Debate agents, document grader, state machine, tool call chain, agent as tool |
| 41-44 | React agent variants | Basic, system prompt, multi-model, context condensation |

**LangChain Examples (25 examples)**

| # | Example | Features Covered |
|---|---------|-----------------|
| 01 | `hello_world` | Basic AgentExecutor compiled to agentspan |
| 02 | `react_with_tools` | ReAct agent with tools |
| 03-07 | Core patterns | Custom tools, structured output, prompt templates, chat history, memory |
| 08-15 | Domain agents | Multi-tool, math, web search, code review, document summarizer, customer service, research, data analyst |
| 16-20 | Content & data | Content writer, SQL agent, email drafter, fact checker, translation |
| 21-25 | Analysis | Sentiment, classification, recommendation, output parsers, advanced orchestration |

**OpenAI Agents SDK Examples (10 examples)**

| # | Example | Features Covered |
|---|---------|-----------------|
| 01 | `basic_agent` | Basic Agent compiled to agentspan |
| 02 | `function_tools` | Function tool definitions |
| 03 | `structured_output` | Typed output |
| 04 | `handoffs` | Agent handoffs |
| 05 | `guardrails` | Input/output guardrails |
| 06 | `model_settings` | Temperature, max tokens |
| 07 | `streaming` | Streaming events |
| 08 | `agent_as_tool` | Sub-agent as tool |
| 09 | `dynamic_instructions` | Runtime instruction modification |
| 10 | `multi_model` | Multiple model providers |

**Google ADK Examples (35 examples)**

| # | Example | Features Covered |
|---|---------|-----------------|
| 00 | `hello_world` | Minimal ADK agent |
| 01-05 | Core patterns | Basic agent, function tools, structured output, sub-agents, generation config |
| 06-10 | Execution | Streaming, output key state, instruction templating, multi-tool, hierarchical |
| 11-15 | Strategies | Sequential, parallel, loop, callbacks, global instruction |
| 16-20 | Domain agents | Customer service, financial advisor, order processing, supply chain, blog writer |
| 21-25 | Advanced | Agent tool, transfer control, callbacks, planner, security |
| 26-32 | Safety & patterns | Safety guardrails, security agent, movie pipeline, include contents, thinking, shared state, nested strategies |
| 33-35 | Real-world | Software bug assistant, ML engineering, RAG agent |

**Vercel AI SDK Examples (TypeScript only)**

Since the Vercel AI SDK is TypeScript-specific, these examples only apply to the TypeScript SDK:

| # | Example | Features Covered |
|---|---------|-----------------|
| 01 | `basic_agent` | Vercel AI SDK agent compiled to agentspan |
| 02 | `tools_compat` | Mix AI SDK + native tools |
| 03 | `streaming` | Stream Vercel AI SDK agent events |
| 04 | `structured_output` | Zod schema output |
| 05 | `multi_step` | Multi-step agent loop |
| 06 | `middleware` | Middleware + agentspan guardrails |
| 07 | `stop_conditions` | stopWhen + agentspan termination |
| 08 | `agent_handoff` | Vercel AI → native agent handoff |
| 09 | `credentials` | Credential injection |
| 10 | `hitl` | HITL with Vercel AI SDK agent |

#### Example Parity Rules

1. **Every Python example must have an equivalent** in each new SDK, translated to idiomatic target-language patterns
2. **File naming**: Use the same numbering and naming convention as Python (e.g., `01_basic_agent.py` → `01-basic-agent.ts` or `01_basic_agent.go`)
3. **Framework examples are language-specific**: TypeScript gets Vercel AI SDK examples in addition to LangGraph/LangChain. Go/Java/Kotlin/C#/Ruby get equivalent framework examples for their language ecosystems when available.
4. **Each example must be self-contained and runnable** with minimal setup (just env vars)
5. **Helper files** (settings, run_all) should be ported as appropriate for the language's idioms
6. **Kitchen sink** remains the single acceptance test exercising all features in one workflow

#### HARD REQUIREMENT: Framework Examples Must Use Real Native SDKs

**Framework examples (LangGraph, LangChain, OpenAI Agents, Google ADK, Vercel AI SDK) MUST import and use the REAL framework packages — never mocks or duck-typed stand-ins.** This is a non-negotiable requirement for all language SDKs.

**Rationale:** The entire value proposition of framework integration is "take your existing framework code, run it on agentspan." If examples use mocks, they prove nothing — they only test the detection duck-typing, not the actual compiled execution. Users need real, runnable examples they can copy and adapt.

**What this means:**

1. **Install real framework packages** as dev/optional dependencies:
   - TypeScript: `ai`, `@ai-sdk/openai`, `@langchain/core`, `@langchain/langgraph`, `@langchain/openai`
   - Python: `langchain`, `langgraph`, `openai-agents`, `google-adk` (already done)
   - Go/Java/Kotlin/C#/Ruby: equivalent packages for their ecosystems when available

2. **Each framework example must:**
   - Import from the real framework package (e.g., `import { generateText } from 'ai'`, not a mock)
   - Create a real framework agent/graph/executor using the framework's native API
   - Pass that real object to `runtime.run()` for agentspan execution
   - Include TWO execution paths for validation comparison:
     ```
     // Path 1: Native framework execution (baseline)
     const nativeResult = await agent.generate({ prompt });

     // Path 2: Agentspan compiled execution (what we're testing)
     const agentspanResult = await runtime.run(agent, prompt);

     // Compare results
     ```

3. **Validation must compare native vs agentspan execution:**
   - Both should complete successfully
   - Tool calls should match (same tools invoked)
   - Output should be semantically similar (LLM judge comparison)
   - The validation framework's per-framework groups (LANGGRAPH, LANGCHAIN, VERCEL_AI, etc.) should run these comparisons

4. **If a framework package is not available or incompatible** for the target language, **do not ship those framework examples**. Remove them entirely — do not substitute mocks, stubs, or duck-typed stand-ins. Document the gap with a tracking issue that specifies what dependency change is needed (e.g., "Blocked on Zod v4 migration — `@openai/agents` v0.8 and `@google/adk` v0.5 require Zod v4"). The examples are added back only when the real SDK can be imported and executed.

5. **No mocks, ever.** This is absolute. If an example file exists in the `examples/` directory for a framework, it MUST use real imports from that framework's package. If the package can't be installed, the example file must not exist. A missing example is honest; a mock example is misleading and will be copied by users who expect it to work.

6. **Framework packages are dev/optional dependencies** — they must NOT be required for core SDK functionality. Only needed to run framework-specific examples and validation.

---

## 13. Success Criteria

A new language SDK is considered complete when:

1. All 89 features in the traceability matrix are implemented
2. Kitchen sink workflow produces identical AgentConfig JSON
3. Kitchen sink execution completes successfully with all stages
4. All test assertions pass
5. LLM judge scores ≥ threshold on all rubrics
6. Validation framework runs with HTML report generation
7. Native SDK comparison shows semantic equivalence
8. Both sync and async APIs work correctly
9. Documentation covers all public APIs
10. Package is publishable to the language's package registry
11. Framework integration works (TypeScript: Vercel AI SDK agents compiled to agentspan workflows; Python: LangGraph/LangChain compiled to agentspan workflows)
12. **All Python examples ported** — every native example (97) + framework examples (LangGraph 44, LangChain 25, OpenAI 10, ADK 35) have idiomatic equivalents per §12.1

---

## 14. Addendum: Implementation Details (from 3-pass review)

This section documents critical implementation details discovered during a thorough 3-pass review of the Python SDK source, all examples (agentspan, LangChain, LangGraph, OpenAI, ADK), and server-side code. These details are **required for SDK correctness** and were not covered in the original spec.

### 14.1 Type Coercion Rules (Worker Dispatch)

Every SDK must coerce tool input values from Conductor's type system to the target language's type system. The rules must be applied **in order**:

1. **Null/empty check:** If value is null or target type is unknown, return value unchanged
2. **Optional unwrapping:** If target type is `Optional<X>`, extract `X` and recurse
3. **Type match short-circuit:** If value already matches target type, return unchanged
4. **String → list/dict via JSON:** If value is string and target is list/dict, try `JSON.parse(value)`. On failure, return original string (silent fallback)
5. **dict/list → string via JSON:** If value is dict/list and target is string, try `JSON.stringify(value)`. **Reason:** Conductor delivers AI_MODEL arguments as parsed objects; tools expecting JSON strings must re-serialize
6. **String → int/float/bool:** Try conversion. Boolean: `"true"/"1"/"yes" → true`, `"false"/"0"/"no" → false`. On failure, return original string
7. **Fallback:** Return original value unchanged

**All coercion failures are silent** — return original value, never throw.

Python reference: `sdk/python/src/agentspan/agents/runtime/_dispatch.py:_coerce_value()`

### 14.2 Circuit Breaker

Tools that fail consecutively are automatically disabled to prevent cascading failures.

| Setting | Value |
|---------|-------|
| Threshold | 10 consecutive failures |
| Reset | On any successful execution (counter → 0) |
| Scope | Per tool name, module-level (persists across workflows) |
| Behavior when open | Immediate `RuntimeError`, no execution attempt |
| Manual reset | `reset_circuit_breaker(tool_name)` or `reset_all_circuit_breakers()` |

### 14.3 Worker Naming Conventions

The SDK generates these Conductor task names for system workers. The **server expects exact names** for routing.

| Worker Type | Name Pattern | Created When |
|-------------|--------------|-------------|
| Tool | `{tool.name}` | Always (for `@tool` functions) |
| Tool-level guardrail | `{guardrail.name}` | Tool has guardrails |
| Output guardrail wrapper | `{agent_name}_output_guardrail` | Agent has custom guardrails |
| stop_when | `{agent_name}_stop_when` | `agent.stop_when` is callable |
| termination | `{agent_name}_termination` | `agent.termination` is set |
| gate | `{agent_name}_gate` | `agent.gate` is callable |
| check_transfer | `{agent_name}_check_transfer` | Agent has both tools AND sub-agents |
| router_fn | `{agent_name}_router_fn` | Strategy=ROUTER and router is callable |
| handoff_check | `{agent_name}_handoff_check` | `agent.handoffs` is non-empty |
| process_selection | `{agent_name}_process_selection` | Strategy=MANUAL |
| Callback | `{agent_name}_{position}` | Callback handler exists for that position |

Worker names are collected recursively through nested agents (including `agent_tool()` sub-agents).

### 14.4 Additional HTTP Payload Fields

The `POST /agent/start` payload includes fields not previously documented:

```json
{
  "agentConfig": { ... },
  "prompt": "user input",
  "sessionId": "",
  "media": [],
  "idempotencyKey": "optional-key",
  "timeoutSeconds": 300,
  "credentials": ["CRED_A", "CRED_B"]
}
```

**Rules:**
- `sessionId`: **Always present** in payload. Empty string `""` if not provided (never omitted)
- `idempotencyKey`: **Only present** if explicitly provided. Omitted if null
- `media`: **Always present**. Empty array `[]` if not provided. Contains list of media URLs (strings)
- `timeoutSeconds`: Only present if provided. Overrides agent-level `timeout_seconds`
- `credentials`: Only present if provided. Agent-level credential declarations

### 14.5 Idempotency Semantics

When `idempotencyKey` is provided:
1. Server maps it to Conductor's `correlationId`
2. Server searches for existing workflow with same agent name + correlationId
3. Search scope: **RUNNING or COMPLETED** workflows only (not FAILED)
4. If found: returns existing `workflowId` without re-execution
5. If not found: creates new execution with `correlationId = idempotencyKey`

**Key behavior:** Failed workflows are NOT deduplicated — a new execution is created.

### 14.6 ToolContext.state Mutation Capture

When a tool modifies `ToolContext.state`, the SDK captures mutations and appends them to the tool result:

```json
{
  "original_result_key": "value",
  "_state_updates": {
    "key1": "new_value",
    "key2": [1, 2, 3]
  }
}
```

**Rules:**
- Key name: `_state_updates` (underscore prefix)
- Only included if `state` is non-empty after tool execution
- If tool result is a dict: merged into the dict
- If tool result is not a dict: wrapped as `{"result": <original>, "_state_updates": {...}}`
- Server extracts `_state_updates`, persists state, removes key from user-visible output

### 14.7 Framework Event Push Wire Format

Framework agent workers push events to `POST /agent/{workflowId}/events`:

```json
[
  {"type": "thinking", "content": "reasoning text"},
  {"type": "tool_call", "toolName": "search", "args": {"input": "query"}},
  {"type": "tool_result", "toolName": "search", "result": "result text"},
  {"type": "context_condensed", "trigger": "reason", "messagesBefore": 50, "messagesAfter": 20},
  {"type": "subagent_start", "subWorkflowId": "uuid", "prompt": "text"},
  {"type": "subagent_stop", "subWorkflowId": "uuid", "result": "text"}
]
```

**Only these 6 event types are supported.** Unknown types are silently dropped by the server.

Headers: Same auth headers as other endpoints (`Authorization`, `X-Auth-Key`/`X-Auth-Secret`).

### 14.8 correlation_id

- **Auto-generated** by the SDK as a UUID for every `run()`/`start()`/`stream()` call
- **Not user-provided** (no parameter)
- Stored in `AgentHandle.correlation_id` and propagated to `AgentResult.correlation_id`
- Used for client-side tracing only (not sent to server unless via `idempotencyKey`)

### 14.9 Gate Condition Behavior

Gates are inserted **between sequential pipeline stages** by the server compiler:

**Text gate:** Compiled to INLINE JavaScript task
- Input: previous stage output + gate config (text, caseSensitive)
- Output: `{"decision": "continue"}` or `{"decision": "stop"}`
- Default `caseSensitive: true`

**Worker gate:** Compiled to SIMPLE task
- Worker receives previous stage output as input
- **Must return** `{"decision": "continue"}` or `{"decision": "stop"}`

If gate returns `"stop"`, the sequential pipeline **terminates early**.

### 14.10 required_tools Enforcement

When `required_tools` is set, the server wraps the agent's main loop in an **outer DO_WHILE**:

1. Agent executes normally (inner loop)
2. INLINE JavaScript task checks if all `required_tools` were called (via `completedTaskNames`)
3. If not all called: re-execute agent (up to **3 outer iterations**)
4. After 3 failures: workflow completes with whatever results are available

**Impact:** `required_tools` can triple execution time in worst case.

### 14.11 Tool Execution Model

| Tool Type | Executed By | Worker Needed |
|-----------|------------|---------------|
| `worker` | SDK worker (Conductor SIMPLE) | **Yes** |
| `http` | Server (Conductor HTTP) | No |
| `api` | Server (LIST_API_TOOLS discovery → Conductor HTTP) | No |
| `mcp` | Server (Conductor CALL_MCP_TOOL) | No |
| `agent_tool` | Server (Conductor SUB_WORKFLOW) | Depends on sub-agent |
| `human` | Server (Conductor HUMAN) | No |
| `generate_image` | Server (Conductor GENERATE_IMAGE) | No |
| `generate_audio` | Server (Conductor GENERATE_AUDIO) | No |
| `generate_video` | Server (Conductor GENERATE_VIDEO) | No |
| `generate_pdf` | Server (Conductor GENERATE_PDF) | No |
| `rag_index` | Server (Conductor LLM_INDEX_TEXT) | No |
| `rag_search` | Server (Conductor LLM_SEARCH_INDEX) | No |

**Critical:** Media tools (`generate_*`) and RAG tools are **server-side only**. SDKs must NOT attempt to execute them as worker tasks.

### 14.12 Event Filtering

Before exposing `AgentEvent` to users, SDKs must strip internal Conductor keys from tool `args`:

**Keys to strip:** `_agent_state`, `method`

These are injected by Conductor for internal routing and should not appear in user-facing events.

### 14.13 Result Normalization

`AgentResult.output` must always be a dict. SDKs must normalize:

| Input | Output |
|-------|--------|
| `dict` | Return as-is |
| `string` (on success) | `{"result": "<string>"}` |
| `null` (on success) | `{"result": null}` |
| `string` (on failure) | `{"error": "<string>", "status": "FAILED"}` |
| `null` (on failure) | `{"error": "Unknown error", "status": "FAILED"}` |

### 14.14 Sequential Agent Flattening (`>>` operator)

When agents are chained with `>>`, the SDK **flattens** the result:

```
a >> b >> c  →  Agent(name="a_b_c", strategy=SEQUENTIAL, agents=[a, b, c])
```

NOT:
```
a >> b >> c  →  Agent(agents=[Agent(agents=[a, b]), c])  # WRONG — no nesting
```

Both sides are flattened: if `a >> b` produces a sequential agent, then `(a >> b) >> c` expands to `[a, b, c]`, not `[sequential(a,b), c]`.

### 14.15 Swarm Transfer Tools (Auto-Generated)

When strategy is `SWARM`, the server **automatically generates** `transfer_to_{agent_name}` tool definitions for each sub-agent. SDKs should NOT manually add these — they are created during compilation.

### 14.16 Execution Token Extraction

Workers extract the execution token from task input for credential resolution:

```json
{
  "tool_arg_1": "value",
  "__agentspan_ctx__": {
    "execution_token": "base64url.payload.signature",
    "workflow_id": "uuid",
    "session_id": "optional"
  }
}
```

**Primary path:** `task.input_data.__agentspan_ctx__.execution_token`
**Fallback:** `task.workflow_input.__agentspan_ctx__.execution_token`

The `__agentspan_ctx__` field is injected by the server and must be stripped before passing args to the tool function.

---

## 15. Lessons Learned: TypeScript SDK Implementation (2026-03-24)

Findings from a 3-pass audit of the first non-Python SDK implementation. Future SDKs should use this as a checklist.

### 15.1 Worker Registration Parity Is the #1 Risk

The serializer and runtime must stay in sync. Every `taskName` the serializer emits **must** have a corresponding worker registered in the runtime. The TypeScript SDK had 6 worker types that were serialized but never registered:

| Worker | Task Name | Impact |
|--------|-----------|--------|
| Termination | `{agent}_termination` | Agent never stops — 300s timeout |
| Custom guardrail | `{guardrail.name}` | Agent never completes — 300s timeout |
| stopWhen | `{agent}_stop_when` | Agent never stops |
| Callbacks | `{agent}_{position}` | Lifecycle hooks silently fail |
| Gate (callable) | `{agent}_gate` | Pipeline gate never evaluated |
| Router (function) | `{agent}_router_fn` | Router never selects agent |

**Checklist for new SDKs:** After implementing the serializer, grep for every `taskName` reference and verify each one has a matching worker registration. Cross-reference against `docs/worker-types.md`.

### 15.2 Class Instance Serialization Requires Normalization

When SDK types use class instances (e.g., `RegexGuardrail`, `LLMGuardrail`) that have a `toWireFormat()` or `toGuardrailDef()` method, the serializer **must** call that method before reading properties. The TypeScript serializer initially read raw instance properties directly, missing fields like `guardrailType` that only exist on the normalized output.

**Rule:** If any SDK type has a normalization method (`toGuardrailDef()`, `toJSON()`, etc.), the serializer must detect and call it. Use duck-typing: `if (typeof obj.toGuardrailDef === 'function')`.

### 15.3 Callback Worker Arguments Must Match Handler Signatures

The server sends generic `{messages, llm_result}` for all callback positions. The SDK's callback handler interface may define typed method signatures like `onModelStart(agentName, messages)`. The worker must bridge these — extracting `agentName` from the registration context (captured in closure) and mapping server fields to the correct positional arguments.

**Rule:** The worker knows `agentName` at registration time. Pass it as the first argument. Map `messages` or `llm_result` from server input to the second argument based on position.

### 15.4 Termination Conditions Need Evaluation Logic, Not Just Serialization

Termination conditions must implement a `shouldTerminate(context)` method that the SDK-side worker calls. Serialization (for the wire format) and evaluation (for the worker) are two separate concerns. The TypeScript SDK initially only had `toJSON()` and forgot `shouldTerminate()`.

**Rule:** Every `TerminationCondition` subclass needs both `toJSON()` (wire format) and `shouldTerminate(context)` (worker evaluation). The return must be `{shouldTerminate: bool, reason: string}`, mapped to `{should_continue: !shouldTerminate, reason}` for the server.

### 15.5 Server-Side vs SDK-Side Workers

Not all Python worker types need SDK-side registration. Some are handled by the server for non-Python SDKs:

| Worker | Python SDK | Other SDKs | Reason |
|--------|-----------|------------|--------|
| Check Transfer (#8) | SDK-side | Server-side | Server inspects tool_calls internally |
| Handoff Check (#10) | SDK-side | Server-side | Declarative conditions evaluated by server |
| Swarm Transfer (#11) | SDK-side | Server-side | Auto-generated by server (§14.15) |
| Manual Selection (#12) | SDK-side | Server-side | Server handles HITL selection |

**How to verify:** If examples using these features (e.g., handoff, swarm) pass WITHOUT SDK workers, the server handles them. Don't add unnecessary workers — they could conflict with server-side logic.

### 15.6 Framework Detection Must Prioritize Native Agent

When an SDK supports multiple frameworks, the detection order matters:

```
1. instanceof NativeAgent  → native path (highest priority)
2. Framework markers       → framework passthrough
3. Default                 → error
```

The native `Agent` check must come first. Duck-typing for framework markers (e.g., checking for `.invoke()` method) can produce false positives if a native Agent happens to have similar properties.

### 15.7 Tool-Level Guardrails Are Separate From Agent-Level

Guardrails can appear in two places:
1. `agent.guardrails` — validated during agent execution
2. `tool.guardrails` — validated before/after tool execution

The runtime must collect and register workers for **both**. The TypeScript SDK initially only registered agent-level guardrail workers and missed tool-level ones.

### 15.8 Drop-In Import Wrappers Are the Best Onboarding Story

For framework integrations (Vercel AI, LangChain, etc.), the ideal onboarding is a single import change:

```typescript
// Before: import { generateText } from 'ai';
// After:
import { generateText } from '@agentspan/sdk/vercel-ai';
```

This is better than requiring users to rewrite their agent as `new Agent({...})`. The wrapper internally builds an Agent, runs it, and maps the result back to the framework's format. Reserve the explicit Agent API for when users need agentspan-specific features (guardrails, termination, handoffs, HITL).

### 15.9 Audit Methodology

For each new SDK, run this 3-pass audit:

1. **Pass 1 — Feature coverage:** Check every feature area (HITL, SSE, credentials, guardrails, all tool types, memory, termination) against the spec. Identify missing worker registrations.
2. **Pass 2 — Edge cases:** Verify fixes from Pass 1. Check argument signatures match between server input and handler interfaces. Check for serialization normalization gaps. Check for race conditions in async registration.
3. **Pass 3 — End-to-end trace:** Pick 2-3 examples that exercise different features. Trace the full flow: Agent → serializer → wire format → runtime → worker registration → server dispatch → worker execution. Verify every step produces correct output.
