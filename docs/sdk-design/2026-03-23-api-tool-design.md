# API Tool Design Spec — Auto-Discovery from OpenAPI, Swagger & Postman

**Date:** 2026-03-23
**Status:** Approved

---

## Overview

Add `api_tool()` to the Agentspan SDK — a single function that points to an OpenAPI spec, Swagger spec, Postman collection, or bare base URL, and automatically discovers all API operations as agent tools. Mirrors the existing `mcp_tool()` pattern: discover at workflow startup, filter with LLM if too many, execute as standard HTTP tasks.

## Motivation

The current `http_tool()` requires manually defining each API endpoint (name, URL, method, headers, input schema). For APIs with dozens or hundreds of endpoints (Stripe, GitHub, Slack), this is impractical. MCP tools already solve this with auto-discovery — `api_tool()` brings the same pattern to HTTP APIs.

---

## 1. SDK API

### `api_tool()` Function

```python
from agentspan.agents import api_tool

# OpenAPI 3.x spec
stripe = api_tool(
    url="https://api.stripe.com/openapi.json",
    headers={"Authorization": "Bearer ${STRIPE_KEY}"},
    credentials=["STRIPE_KEY"],
    max_tools=20,
)

# Swagger 2.0 spec
legacy = api_tool(
    url="https://petstore.swagger.io/v2/swagger.json",
    max_tools=10,
)

# Postman collection
slack = api_tool(
    url="https://api.getpostman.com/collections/12345",
    headers={"Authorization": "Bearer ${SLACK_TOKEN}"},
    credentials=["SLACK_TOKEN"],
)

# Base URL — auto-discovers spec at known paths
weather = api_tool(
    url="https://api.weather.com",
    tool_names=["getCurrentWeather", "getForecast"],
)

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[stripe, slack, weather])
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | str | required | URL to OpenAPI spec, Postman collection, or base URL |
| `name` | str | None | Override name (default: derived from spec `info.title`) |
| `description` | str | None | Override description (default: from spec `info.description`) |
| `headers` | dict | None | Global headers applied to ALL discovered endpoints |
| `credentials` | list | None | Credential names for `${NAME}` header substitution |
| `tool_names` | list | None | Whitelist — only include these operation IDs |
| `max_tools` | int | 64 | If operations exceed this, filter LLM selects most relevant |

### Serialization

Produces `ToolDef(tool_type="api", config={...})`:

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

---

## 2. Server-Side Discovery

### New Conductor System Task: `LIST_API_TOOLS`

Inserted into the workflow **before the agent loop** (same position as `LIST_MCP_TOOLS`).

**Input:**
```json
{
  "specUrl": "https://api.stripe.com/openapi.json",
  "headers": {"Authorization": "Bearer resolved-key"}
}
```

**Action:**
1. HTTP GET the `specUrl` with provided headers
2. Auto-detect format from response content
3. Parse spec and extract operations
4. Return normalized tool descriptors

**Output:**
```json
{
  "tools": [
    {
      "name": "createCustomer",
      "description": "Creates a new customer object",
      "inputSchema": {
        "type": "object",
        "properties": {
          "email": {"type": "string"},
          "name": {"type": "string"}
        },
        "required": ["email"]
      },
      "method": "POST",
      "path": "/v1/customers"
    }
  ],
  "baseUrl": "https://api.stripe.com",
  "format": "openapi3"
}
```

### Format Auto-Detection

| Signal | Format |
|---|---|
| JSON with `"openapi"` field starting with `"3."` | OpenAPI 3.x |
| JSON with `"swagger"` field equal to `"2.0"` | Swagger 2.0 |
| JSON with `"info"."_postman_id"` or root `"item"` array | Postman Collection v2.1 |
| URL returns HTML or 404 | Base URL — try known spec paths |

### Base URL Auto-Discovery

When the URL doesn't return a parseable spec, try these paths in order:

1. `{url}/openapi.json`
2. `{url}/swagger.json`
3. `{url}/v3/api-docs`
4. `{url}/swagger/v1/swagger.json`
5. `{url}/api-docs`
6. `{url}/.well-known/openapi.json`

First successful response is used. If none succeed, the task fails with a descriptive error.

### OpenAPI 3.x → Tool Mapping

| OpenAPI Field | Tool Spec Field |
|---|---|
| `operationId` | `name` (fallback: `{method}_{path_slug}`) |
| `summary` (or `description`) | `description` |
| `parameters` (path, query, header) + `requestBody` | `inputSchema` (merged JSON Schema) |
| `servers[0].url` + `path` | `baseUrl` + `path` (stored in apiConfig) |
| HTTP method | `method` (stored in apiConfig) |

### Swagger 2.0 → Tool Mapping

Same as OpenAPI 3.x, except:
- `host` + `basePath` + `path` → `baseUrl` + `path`
- `parameters` with `in: body` → request body schema
- `consumes`/`produces` → content type headers

### Postman Collection → Tool Mapping

| Postman Field | Tool Spec Field |
|---|---|
| `item[].name` | `name` (slugified) |
| `item[].request.description` | `description` |
| `item[].request.url` | `baseUrl` + `path` extracted |
| `item[].request.method` | `method` |
| `item[].request.body.raw` (JSON Schema inferred) | `inputSchema` |

For nested Postman folders (`item[].item[]`), flatten with `{folder}_{item}` naming.

---

## 3. Compilation Pipeline

Reuses the existing MCP discovery chain pattern in `ToolCompiler.java`:

```
Workflow Start
│
├─ LIST_MCP_TOOLS (for mcp_tool definitions)     ← existing
├─ LIST_API_TOOLS (for api_tool definitions)      ← NEW
│
├─ INLINE prepare task
│    - Merge MCP tools + API tools + static tools (http_tool, worker)
│    - Build mcpConfig map (existing)
│    - Build apiConfig map: { toolName → { baseUrl, method, path, headers } }  ← NEW
│    - Check total_tools > maxTools threshold
│
├─ SWITCH threshold (if exceeded)
│    - Filter LLM selects top N most relevant     ← reused
│
├─ INLINE resolve task
│    - Output: { tools, mcpConfig, apiConfig }
│
└─ Agent Loop Starts
     LLM sees unified tool list (doesn't know which are API vs MCP vs worker)
```

### `apiConfig` Structure

Built by the prepare task from `LIST_API_TOOLS` output:

```json
{
  "createCustomer": {
    "baseUrl": "https://api.stripe.com",
    "method": "POST",
    "path": "/v1/customers",
    "headers": {"Authorization": "Bearer resolved-key", "Content-Type": "application/json"}
  },
  "getCustomer": {
    "baseUrl": "https://api.stripe.com",
    "method": "GET",
    "path": "/v1/customers/{customer_id}",
    "headers": {"Authorization": "Bearer resolved-key"}
  }
}
```

---

## 4. Tool Enrichment & Execution

Added to existing `enrichToolsScript` in `JavaScriptBuilder.java`:

```javascript
// Existing: httpCfg for http_tool, mcpCfg for mcp_tool
// New: apiCfg for api_tool

if (apiCfg[toolName]) {
    var api = apiCfg[toolName];
    var uri = api.baseUrl + api.path;

    // Substitute path parameters: /users/{id} → /users/123
    var params = toolCall.inputParameters || {};
    var pathParams = (uri.match(/\{(\w+)\}/g) || []);
    for (var i = 0; i < pathParams.length; i++) {
        var key = pathParams[i].replace(/[{}]/g, '');
        if (params[key] !== undefined) {
            uri = uri.replace(pathParams[i], encodeURIComponent(params[key]));
            delete params[key];  // consumed — don't send in body
        }
    }

    // Query parameters for GET/DELETE, body for POST/PUT/PATCH
    var method = api.method.toUpperCase();
    var body = null;
    if (method === 'GET' || method === 'DELETE' || method === 'HEAD') {
        // Append remaining params as query string
        var qs = Object.keys(params).map(function(k) {
            return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
        }).join('&');
        if (qs) uri = uri + '?' + qs;
    } else {
        body = params;
    }

    t.type = 'HTTP';
    t.inputParameters = {
        http_request: {
            uri: uri,
            method: method,
            headers: api.headers,
            body: body,
            accept: 'application/json',
            contentType: 'application/json',
            connectionTimeOut: 30000,
            readTimeOut: 30000
        }
    };
}
```

**Key:** API tools execute as standard Conductor `HTTP` tasks. No new task type for execution — only `LIST_API_TOOLS` is new.

### Parameter Placement Rules

| OpenAPI `in` | Enrichment Behavior |
|---|---|
| `path` | Substituted into URI template (`/users/{id}` → `/users/123`) |
| `query` | Appended as query string for GET/DELETE/HEAD |
| `header` | Merged into request headers |
| `body` / `requestBody` | Sent as JSON body for POST/PUT/PATCH |

For GET/DELETE/HEAD requests: all non-path params become query parameters.
For POST/PUT/PATCH requests: all non-path params become the JSON body.

---

## 5. Changes Required

### Python SDK (`sdk/python/src/agentspan/agents/tool.py`)

Add `api_tool()` function (~40 lines):
- Validates `url` is provided
- Validates credential placeholder `${NAME}` references in headers
- Returns `ToolDef(tool_type="api", config={url, headers, tool_names, max_tools})`

### Server: New System Task (`LIST_API_TOOLS`)

New Java class implementing Conductor's `WorkflowSystemTask`:
- HTTP fetch with configurable headers and timeout
- Format auto-detection (OpenAPI 3.x, Swagger 2.0, Postman, base URL)
- OpenAPI parser → normalized tool descriptors
- Swagger 2.0 parser → normalized tool descriptors
- Postman parser → normalized tool descriptors
- Base URL discovery (try known paths)

**Dependencies:** No new dependencies. Use existing `HttpClient` for fetching. JSON parsing via Jackson.

### Server: ToolCompiler Updates

- Add `"api"` to `TYPE_MAP` (maps to `"HTTP"` for execution)
- Add `buildApiDiscoveryTasks()` method (mirrors `buildMcpDiscoveryTasks()`)
- Update `mcpPrepareScript` → `prepareScript` to also handle `apiConfig`
- Update `enrichToolsScript` to include `apiCfg` routing

### Server: JavaScriptBuilder Updates

- Add `apiCfg` variable to enrichment script
- Add path parameter substitution logic
- Add query string construction for GET/DELETE

### Multi-Language SDK Specs

- Add `api_tool` to `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` Section 4.2
- Add to traceability matrix as feature #89
- Update per-language translation guides

---

## 6. Wire Format

### AgentConfig (SDK → Server)

```json
{
  "tools": [
    {
      "name": "stripe_api",
      "toolType": "api",
      "config": {
        "url": "https://api.stripe.com/openapi.json",
        "headers": {"Authorization": "Bearer ${STRIPE_KEY}"},
        "tool_names": null,
        "max_tools": 20,
        "credentials": ["STRIPE_KEY"]
      }
    }
  ]
}
```

### LIST_API_TOOLS Task (Server Internal)

```json
{
  "type": "LIST_API_TOOLS",
  "taskReferenceName": "list_api_stripe",
  "inputParameters": {
    "specUrl": "${workflow.input.api_config.stripe.url}",
    "headers": "${workflow.input.api_config.stripe.headers}"
  }
}
```

### Enriched HTTP Task (Runtime)

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

---

## 7. Error Handling

| Error | Behavior |
|---|---|
| Spec URL unreachable | `LIST_API_TOOLS` fails → workflow fails with descriptive error |
| Spec URL returns invalid format | Same — fail with "Could not detect format at {url}" |
| Base URL — no spec found at any known path | Same — fail with "No OpenAPI/Swagger spec found at {url}" |
| Spec parses but has 0 operations | Warning logged, empty tools list (agent works with other tools) |
| Credential resolution fails for headers | Task fails with `CredentialNotFoundError` |
| Filter LLM fails (when max_tools exceeded) | Fallback: use all tools (log warning) |

---

## 8. Example Usage

### Simple: Weather API

```python
from agentspan.agents import Agent, AgentRuntime, api_tool

weather = api_tool(url="https://api.weather.com")

agent = Agent(name="weather_bot", model="openai/gpt-4o", tools=[weather])

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    result.print_result()
```

### With Credentials: Stripe

```python
stripe = api_tool(
    url="https://api.stripe.com/openapi.json",
    headers={"Authorization": "Bearer ${STRIPE_KEY}"},
    credentials=["STRIPE_KEY"],
    max_tools=20,  # Stripe has 300+ ops — filter to top 20
)

agent = Agent(name="billing", model="openai/gpt-4o", tools=[stripe])
```

### Whitelisted Operations: GitHub

```python
github = api_tool(
    url="https://api.github.com",
    headers={"Authorization": "token ${GITHUB_TOKEN}"},
    credentials=["GITHUB_TOKEN"],
    tool_names=["repos_list_for_user", "repos_create", "issues_list", "issues_create"],
)
```

### Postman Collection

```python
internal_api = api_tool(
    url="https://api.getpostman.com/collections/12345?apikey=xxx",
    headers={"X-Internal-Auth": "${INTERNAL_KEY}"},
    credentials=["INTERNAL_KEY"],
)
```

### Mixed Tools: API + MCP + Native

```python
from agentspan.agents import Agent, api_tool, mcp_tool, tool

stripe = api_tool(url="https://api.stripe.com/openapi.json", credentials=["STRIPE_KEY"])
github = mcp_tool(server_url="http://localhost:3001/mcp", credentials=["GITHUB_TOKEN"])

@tool
def calculate(expression: str) -> dict:
    return {"result": eval(expression)}

agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[stripe, github, calculate],
)
```

The LLM sees all tools uniformly — it doesn't know which are API-discovered, MCP-discovered, or native Python.
