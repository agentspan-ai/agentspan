# API Design

**Status:** Consolidated 2026-06-26

**Scope.** This is the canonical reference for the **SDK-facing API surface** — how every
language SDK lets a user declare tools and agents — and for the **wire schema** those SDKs
serialize to and POST to the server. It covers the `AgentConfig` JSON contract, the tool
declaration conventions (`tool` / `httpTool` / `mcpTool` / `apiTool`), the `api_tool()`
auto-discovery feature, and the `Agent(model=...)` model conventions including
`Agent(model="claude-code")`. Detailed REST server endpoints (start/compile/poll, HITL, etc.)
live in [agentspan-design.md](agentspan-design.md); this doc is the SDK + wire API only. See
also [sdk-design.md](sdk-design.md) (multi-language SDK surface),
[framework-integration.md](framework-integration.md) (framework-bridged agents), and
[tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md)
(runtime tool execution and credential resolution).

---

## 1. The API contract

Every SDK exposes the same conceptual surface, regardless of language:

- **Agents** — a single `Agent(...)` constructor declares one agent (model, instructions,
  tools, turn/token limits, guardrails) or a multi-agent group (`agents=[...]` + a
  `strategy`). Agents nest recursively.
- **Tools** — small declarative factory functions (`tool` / `httpTool` / `mcpTool` /
  `apiTool`) attach capabilities to an agent. Each produces a tool descriptor that serializes
  into the `tools` array of `AgentConfig`.
- **Wire schema** — every SDK serializes the above into one JSON document, `AgentConfig`,
  and POSTs it under the `agentConfig` key of the start/compile request. The server
  deserializes it into its `AgentConfig` model and compiles it into a Conductor workflow.

The wire schema is the contract that makes the SDKs interchangeable: a config emitted by the
Python SDK and one emitted by the Java SDK are the same document and compile identically.

---

## 2. AgentConfig wire schema

The canonical wire contract is **[`../sdk/java/docs/agent-schema.json`](../sdk/java/docs/agent-schema.json)**
(JSON Schema Draft 2020-12), documented in
[`../sdk/java/docs/agent-schema.md`](../sdk/java/docs/agent-schema.md). Treat that JSON as the
source of truth; the summary below is a guide, not a redefinition.

**Conventions**

- camelCase keys; absent = unset (server uses `@JsonInclude(NON_NULL)`).
- `additionalProperties: false` at the root — the schema is the *complete* set of recognized
  top-level keys (intentionally stricter than the server, which ignores unknown keys).
- Recursive: `agents`, `planner`, `fallback`, and `router` each nest a full `AgentConfig`
  (`$ref: "#"`).
- The schema describes **native** agent configs. Framework-bridged agents (`openai`,
  `google_adk`, `skill`, …) take a different path — they are sent as an opaque `rawConfig`
  under a `framework` key in the request wrapper and are out of scope here (see
  [framework-integration.md](framework-integration.md)).

**Top-level fields (selected).** `name` is the only required field.

| Field | Type | Purpose |
|---|---|---|
| `name` | string (required) | Agent name (`^[a-zA-Z_][a-zA-Z0-9_-]*$`). |
| `model` | string\|null | `"provider/model"` identifier. Null/omitted for external agents. |
| `external` | boolean | True when the agent has no model and is driven externally. |
| `baseUrl` | string | Per-agent LLM provider endpoint override. |
| `instructions` | string\|object\|null | System prompt — plain string or a prompt-template ref. |
| `tools` | array→`tool` | Tool descriptors (see §3). |
| `agents` | array→`#` | Sub-agents (recursive); requires a `strategy`. |
| `strategy` | string\|null (enum) | Multi-agent orchestration; null for a single agent. |
| `router` | `#`\|`workerRef` | ROUTER strategy router (nested agent or worker task). |
| `guardrails` | array→`guardrail` | Input/output guardrails (see below). |
| `maxTurns` / `maxTokens` / `temperature` / `timeoutSeconds` | int/num | Run limits. |
| `reasoningEffort` | string (enum) | `minimal\|low\|medium\|high` — OpenAI reasoning models only. |
| `contextWindowBudget` | integer | Token threshold for proactive context condensation. |
| `thinkingConfig` / `memory` / `termination` / `outputType` | object | Extended-thinking, message memory, termination conditions, structured-output type. |
| `handoffs` / `allowedTransitions` | array / object | Handoff conditions; SWARM transition map. |
| `callbacks` | array→`callback` | Lifecycle callbacks (before/after agent/model/tool). |
| `gate` / `stopWhen` | object / workerRef | Sequential-pipeline gate; stop condition. |
| `enablePlanning` / `planner` / `fallback` / `fallbackMaxTurns` / `plannerContext` / `planSource` | mixed | PLAN_EXECUTE planning slots. |
| `requiredTools` / `prefillTools` | array | Force-call tools; prefilled tool calls. |
| `credentials` | array<string> | Credential names to resolve for this agent. |
| `codeExecution` / `cliConfig` | object | Sandboxed code execution; CLI execution config. |
| `metadata` / `maskedFields` / `synthesize` / `stateful` / `includeContents` | mixed | Misc orchestration flags. |

**Strategy enum:** `handoff`, `sequential`, `parallel`, `router`, `round_robin`, `random`,
`swarm`, `manual`, `plan_execute` (or `null` for a single agent).

**Tool kinds.** A tool descriptor (`$defs.tool`) carries `name`, `description`,
`inputSchema`/`outputSchema`, a `toolType` discriminator, and a freeform `config` map for
type-specific settings. `toolType` is one of `worker | http | mcp | api | agent_tool | …`
(see §3 for the SDK conventions that produce each). The `tool` definition keeps
`additionalProperties: true` because `config` is freeform and the Java serializer may emit
extra retry fields (`retryCount`, `retryDelaySeconds`, `retryPolicy`).

> **Note.** `toolType` is a free `string` in the schema (it has no `enum`), so `api` validates
> fine even though the schema's `toolType` *description* string
> (`"worker | http | mcp | agent_tool | …"`) does not list it. `api` is the real wire literal
> emitted by `api_tool` (see §3 / §4.1); the description string is illustrative, not exhaustive.

**Guardrails.** A guardrail (`$defs.guardrail`) has a `guardrailType`
(`regex | llm | custom | external | …`), a `position` (`input | output`), an `onFail` policy
(closed enum `retry | raise | fix | human`), and type-specific keys (`patterns`, `mode`,
`model`, `policy`, …). See [guardrails-design.md](guardrails-design.md).

**Nested config models.** The schema defines 16 nested `$defs`: `promptTemplate`, `tool`,
`guardrail`, `termination`, `handoff`, `callback`, `memory`, `message`, `codeExecution`,
`cliConfig`, `thinkingConfig`, `prefillTool`, `plannerContextEntry`, `outputType`, `gate`,
`workerRef`. Most are `additionalProperties: false`; consult the JSON for exact fields.

**Known cross-SDK divergences** (both forms validate against the schema):

- **Static plan channel.** Python places the static plan in `agentConfig.planSource`; Java
  sends it in the request wrapper as `static_plan`.
- **Session id channel.** Java echoes `sessionId` into `agentConfig` *and* the wrapper;
  Python sends it only in the wrapper. The server reads it from the wrapper.
- **`stateful` / `localCodeExecution` / `cliConfig.workingDir`.** SDK-emitted extras the
  server does not model on `AgentConfig` directly but the schema tolerates so SDK output
  validates.

---

## 3. Tool declaration API

Tools are declared with small factory functions. Names below use the Python form; each SDK
mirrors the convention idiomatically (camelCase methods in Java/TS, etc.). All of them
produce a tool descriptor that lands in the `tools` array of `AgentConfig` with a `toolType`
discriminator and a `config` map.

| SDK factory | `toolType` | Declares | Discovery |
|---|---|---|---|
| `tool` / `@tool` | `worker` | A native function/worker that runs in the SDK process. | Static — the function signature defines `inputSchema`. |
| `http_tool` | `http` | A single HTTP endpoint (name, URL, method, headers, input schema). | Static — you define the one endpoint. |
| `mcp_tool` | `mcp` | An MCP server; all its tools become agent tools. | Auto — discovered at workflow startup via `LIST_MCP_TOOLS`. |
| `api_tool` | `api` | An OpenAPI/Swagger spec, Postman collection, or base URL; all operations become agent tools. | Auto — discovered at workflow startup via `LIST_API_TOOLS` (see §4). |

**Conventions shared across kinds**

- **Credentials.** Headers may reference credentials with `${NAME}` placeholders; the
  `credentials=[...]` list names which to resolve. Resolution happens server-side at runtime
  (see [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md)).
- **Uniform LLM view.** The model sees one flat tool list and cannot tell which tools are
  native, HTTP, MCP-discovered, or API-discovered — they are all just callable tools.
- **Auto-discovered kinds** (`mcp_tool`, `api_tool`) support a `max_tools` cap; when the
  discovered set exceeds it, a filter LLM selects the most relevant subset at startup.

> **SDK availability.** `api_tool` ships in the **Python, TypeScript, and C#** SDKs but is
> **not present in the Java SDK** (which has `tool` / `httpTool` / `mcpTool` only). The other
> three tool factories (`tool` / `http_tool` / `mcp_tool`) are available in all four SDKs.

```python
from conductor.ai.agents import Agent, api_tool, http_tool, mcp_tool, tool

@tool
def calculate(expression: str) -> dict:        # toolType=worker (native)
    return {"result": eval(expression)}

weather = http_tool(name="getWeather", url="https://api.weather.com/now", method="GET")
github  = mcp_tool(server_url="http://localhost:3001/mcp", credentials=["GITHUB_TOKEN"])
stripe  = api_tool(url="https://api.stripe.com/openapi.json", credentials=["STRIPE_KEY"])

agent = Agent(name="assistant", model="openai/gpt-4o",
              tools=[calculate, weather, github, stripe])
```

---

## 4. `api_tool` — auto-discovery from OpenAPI / Swagger / Postman

`api_tool()` points at an OpenAPI spec, Swagger spec, Postman collection, or bare base URL
and automatically discovers every API operation as an agent tool. It mirrors the `mcp_tool`
pattern (discover at startup, filter with an LLM if too many, execute as standard HTTP tasks),
removing the need to hand-define dozens or hundreds of endpoints with `http_tool`.

### 4.1 SDK API

```python
from conductor.ai.agents import api_tool

# OpenAPI 3.x spec
stripe = api_tool(
    url="https://api.stripe.com/openapi.json",
    headers={"Authorization": "Bearer ${STRIPE_KEY}"},
    credentials=["STRIPE_KEY"],
    max_tools=20,
)

# Swagger 2.0 spec
legacy = api_tool(url="https://petstore.swagger.io/v2/swagger.json", max_tools=10)

# Postman collection
slack = api_tool(
    url="https://api.getpostman.com/collections/12345",
    headers={"Authorization": "Bearer ${SLACK_TOKEN}"},
    credentials=["SLACK_TOKEN"],
)

# Base URL — auto-discovers spec at known paths
weather = api_tool(url="https://api.weather.com",
                   tool_names=["getCurrentWeather", "getForecast"])
```

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | str | required | URL to OpenAPI spec, Postman collection, or base URL. |
| `name` | str | None | Override name (default: from spec `info.title`). |
| `description` | str | None | Override description (default: from spec `info.description`). |
| `headers` | dict | None | Global headers applied to ALL discovered endpoints. |
| `credentials` | list | None | Credential names for `${NAME}` header substitution. |
| `tool_names` | list | None | Whitelist — only include these operation IDs. |
| `max_tools` | int | 64 | If operations exceed this, a filter LLM selects the most relevant. |

**Serialization** — produces a tool descriptor with `toolType: "api"` and a `config` map:

```json
{
  "name": "stripe_api",
  "description": "Stripe payment API",
  "toolType": "api",
  "inputSchema": null,
  "config": {
    "url": "https://api.stripe.com/openapi.json",
    "headers": {"Authorization": "Bearer ${STRIPE_KEY}"},
    "tool_names": null,
    "max_tools": 20,
    "credentials": ["STRIPE_KEY"]
  }
}
```

### 4.2 Server-side discovery: `LIST_API_TOOLS`

A new Conductor system task, inserted before the agent loop (same position as
`LIST_MCP_TOOLS`). It HTTP-GETs the spec URL with the resolved headers, auto-detects the
format, parses operations, and returns normalized tool descriptors plus the base URL.

**Format auto-detection**

| Signal | Format |
|---|---|
| JSON with `"openapi"` field starting `"3."` | OpenAPI 3.x |
| JSON with `"swagger"` field `"2.0"` | Swagger 2.0 |
| JSON with `"info"."_postman_id"` or root `"item"` array | Postman Collection v2.1 |
| URL returns HTML or 404 | Base URL — try known spec paths |

**Base URL auto-discovery** — tries, in order:
`{url}/openapi.json`, `{url}/swagger.json`, `{url}/v3/api-docs`,
`{url}/swagger/v1/swagger.json`, `{url}/api-docs`, `{url}/.well-known/openapi.json`. First
success wins; if none succeed, the task fails with a descriptive error.

**Spec → tool mapping**

- **OpenAPI 3.x:** `operationId` → `name` (fallback `{method}_{path_slug}`); `summary`/
  `description` → `description`; `parameters` (path/query/header) + `requestBody` → merged
  `inputSchema`; `servers[0].url` + `path` → `baseUrl` + `path`; HTTP method → `method`.
- **Swagger 2.0:** as above, except `host` + `basePath` + `path` → `baseUrl` + `path`;
  `in: body` parameters → request body schema; `consumes`/`produces` → content-type headers.
- **Postman:** `item[].name` → slugified `name`; `request.description` → `description`;
  `request.url` → `baseUrl` + `path`; `request.method` → `method`;
  `request.body.raw` (JSON Schema inferred) → `inputSchema`. Nested folders
  (`item[].item[]`) flatten as `{folder}_{item}`.

### 4.3 Compilation pipeline

Reuses the MCP discovery chain (`ToolCompiler.java`):

```
Workflow Start
├─ LIST_MCP_TOOLS (for mcp_tool defs)            ← existing
├─ LIST_API_TOOLS (for api_tool defs)            ← NEW
├─ INLINE prepare task
│    - Merge MCP + API + static tools (http_tool, worker)
│    - Build mcpConfig (existing) + apiConfig: {toolName → {baseUrl, method, path, headers}}
│    - Check total_tools > maxTools
├─ SWITCH threshold (if exceeded) → filter LLM picks top N      ← reused
├─ INLINE resolve task → {tools, mcpConfig, apiConfig}
└─ Agent Loop  (LLM sees one unified tool list)
```

`apiConfig` is keyed by tool name, each entry `{baseUrl, method, path, headers}` with
credentials already resolved into the headers.

### 4.4 Tool enrichment & execution

API tools execute as standard Conductor **`HTTP`** tasks — there is no new execution task
type, only `LIST_API_TOOLS` for discovery. At enrichment time (`enrichToolsScript` in
`JavaScriptBuilder.java`), an `apiCfg[toolName]` entry is routed by:

- Substituting path params into the URI template (`/users/{id}` → `/users/123`); consumed
  params are removed from the body.
- For `GET`/`DELETE`/`HEAD`: remaining params become the query string.
- For `POST`/`PUT`/`PATCH`: remaining params become the JSON body.
- Merging `header` params and the global `headers` into the request headers.

| OpenAPI `in` | Enrichment behavior |
|---|---|
| `path` | Substituted into the URI template. |
| `query` | Query string for GET/DELETE/HEAD. |
| `header` | Merged into request headers. |
| `body` / `requestBody` | JSON body for POST/PUT/PATCH. |

Enriched runtime task:

```json
{
  "type": "HTTP",
  "taskReferenceName": "tool_createCustomer_0",
  "inputParameters": {
    "http_request": {
      "uri": "https://api.stripe.com/v1/customers",
      "method": "POST",
      "headers": {"Authorization": "Bearer sk-resolved-key"},
      "body": {"email": "user@example.com", "name": "Alice"},
      "accept": "application/json",
      "contentType": "application/json"
    }
  }
}
```

### 4.5 Error handling

| Error | Behavior |
|---|---|
| Spec URL unreachable | `LIST_API_TOOLS` fails → workflow fails with descriptive error. |
| Invalid/undetectable format | Fail: "Could not detect format at {url}". |
| Base URL — no spec at any known path | Fail: "No OpenAPI/Swagger spec found at {url}". |
| Spec parses but 0 operations | Warning logged; empty tools list (agent works with other tools). |
| Credential resolution fails | Task fails with `CredentialNotFoundError`. |
| Filter LLM fails (max_tools exceeded) | Fallback: use all tools (log warning). |

---

## 5. Agent model conventions

The `model` field is a `"provider/model"` string (e.g. `"openai/gpt-4o"`,
`"anthropic/claude-sonnet-4-5"`). Null/omitted marks an **external** agent driven outside the
server. Beyond standard providers, the SDK supports a **Claude Code** convention that lets
Claude Agent SDK agents use the same `Agent(...)` interface as native agents — so they
compose as sub-agents, participate in handoffs, and work with sequential/parallel/router
strategies.

> **SDK availability.** The Claude Code convention — the `ClaudeCode` config object and
> `Agent(model="claude-code"|"claude-code/...")` — exists **only in the Python and TypeScript
> SDKs**. It is **not available in the Java or C# SDKs**. Everything in §5 is scoped to those
> two SDKs.

### 5.1 `Agent(model="claude-code")`

```python
from conductor.ai.agents import Agent, ClaudeCode

# Slash syntax (alias resolved to a full model ID)
reviewer = Agent(
    name="reviewer",
    model="claude-code/opus",
    instructions="Review Python code for quality and security",
    tools=["Read", "Glob", "Grep"],
    max_turns=10,
)

# Default model (CLI default)
reviewer = Agent(name="reviewer", model="claude-code", instructions="...", tools=["Read"])

# Config object for permission_mode
reviewer = Agent(
    name="reviewer",
    model=ClaudeCode("opus", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    instructions="Review code",
    tools=["Read", "Edit", "Bash"],
    max_turns=10,
)

# Composition — a native orchestrator with Claude Code sub-agents
pipeline = Agent(name="pipeline", model="anthropic/claude-sonnet-4-5",
                 agents=[reviewer, writer, tester], strategy="sequential")
```

**`ClaudeCode` config** carries a minimal surface — model name + permission mode only:

```python
@dataclass
class ClaudeCode:
    class PermissionMode(str, Enum):
        DEFAULT = "default"
        ACCEPT_EDITS = "acceptEdits"
        PLAN = "plan"
        BYPASS = "bypassPermissions"

    model_name: str = ""                                  # "opus"/"sonnet"/"haiku"/full ID; "" = CLI default
    permission_mode: PermissionMode = PermissionMode.ACCEPT_EDITS
```

No `mcp_servers` and no `hooks` on this config: agentspan injects observability hooks
internally, and the `ClaudeCodeOptions` escape hatch remains for power users who need raw
MCP, hooks, etc. **Phase 1 supports only string (Claude built-in) tools** — passing a custom
`@tool` callable to a `claude-code` agent raises `ValueError`. (Phase 2 will add an MCP bridge
that auto-converts `@tool` functions to MCP servers.)

### 5.2 Model alias resolution

| Input | Resolved model |
|---|---|
| `"claude-code"` | `None` (CLI default) |
| `"claude-code/opus"` | `"claude-opus-4-6"` |
| `"claude-code/sonnet"` | `"claude-sonnet-4-6"` |
| `"claude-code/haiku"` | `"claude-haiku-4-5"` |
| `"claude-code/claude-opus-4-6"` | `"claude-opus-4-6"` (passthrough) |
| `ClaudeCode("opus")` | `"claude-opus-4-6"` |
| `ClaudeCode()` | `None` (CLI default) |

Short aliases map to full model IDs via a dict lookup; unknown aliases pass through as-is.

### 5.3 Where the config lives (architecture)

**The server only ever sees a passthrough stub for a `claude-code` agent.** All real
configuration — instructions, tools, `max_turns`, `permission_mode` — is consumed locally in
the SDK worker closure, not serialized to JSON. The server's role is to create a minimal
workflow with a single SIMPLE task; the worker does the rest.

- Serialization emits a minimal `{name, _worker_name}` raw_config (identical for an `Agent`
  and for a raw `ClaudeCodeOptions`).
- The worker builder converts `Agent(model="claude-code/...")` → a `ClaudeCodeOptions`
  dataclass (`agent_to_claude_code_options()`) before invoking the worker. This conversion is
  **load-bearing**: the worker calls `dataclasses.replace(options, hooks=...)` to merge
  observability hooks, which would crash on a non-dataclass (e.g. an `Agent`).
- **Routing is NOT by framework passthrough.** A native `Agent` is *always* serialized
  natively — even when its `model` is `"claude-code"` / `"claude-code/..."`. `detect_framework()`
  returns `None` for any native `Agent` instance (serializer.py: "Native Agent instances are
  always native, even with claude-code models. The server handles claude-code model routing
  during execution."). `detect_framework()` returns `"claude_agent_sdk"` **only** for a raw
  `ClaudeCodeOptions` / `ClaudeAgentOptions` object (the escape hatch), not for an `Agent`. The
  server routes a `claude-code`-model `Agent` server-side **by model**, not via the framework
  passthrough path.

**Sub-agent composition** requires three coordinated pieces so a `claude-code` agent can sit
inside `agents=[...]`:

1. **Worker prep** — when recursing into sub-agents, detect a `claude-code` sub-agent and
   register a passthrough worker instead of recursing into its (string) tools.
2. **Config serialization** — emit passthrough metadata for the sub-agent
   (`metadata._framework_passthrough = true`, a single `worker`-type tool entry; do *not*
   serialize instructions/tools), matching the shape the framework normalizer produces.
3. **Server compile** — `AgentCompiler` detects a `claude-code` model prefix on a sub-agent
   as a safety net and forces the passthrough compilation path even if metadata was missing.

This convention extends to the framework-bridge machinery documented in
[framework-integration.md](framework-integration.md); the `ClaudeCodeOptions` escape hatch
(`runtime.run(ClaudeCodeOptions(...))`) continues to work unchanged.
