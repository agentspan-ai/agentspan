---
title: Tools
description: Building tools with @tool, http_tool, mcp_tool, api_tool — plus credentials and code execution
---

# Tools

Tools are functions the LLM can call during execution.

**Agentspan ships built-in tools for the most common cases — HTTP endpoints, full OpenAPI specs, and MCP servers — so you don't have to write code for them.** When you need custom logic, decorate any Python function with `@tool` and it's available to the LLM automatically.

| Type | Who writes the code | How it runs | Use when |
|---|---|---|---|
| `@tool` | You | Python worker process | Custom logic, any Python library |
| `http_tool()` | Nobody — configure only | Server-side HTTP task | Single API endpoint |
| `api_tool()` | Nobody — configure only | Server-side, auto-discovered | Full OpenAPI/Swagger/Postman spec |
| `mcp_tool()` | Nobody — configure only | Server-side MCP task | MCP server |

For `http_tool`, `api_tool`, and `mcp_tool`, you provide a URL and optionally credentials. Agentspan handles execution entirely on the server — no worker process, no Python code, nothing to maintain.

## `@tool` — Custom Python Functions

Decorate any Python function to make it a tool:

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    return {"city": city, "temp": 72, "condition": "Sunny"}

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[get_weather])

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    result.print_result()
```

The JSON schema for the LLM is auto-generated from type hints and the docstring. The function also works as a normal Python function: `get_weather("NYC")` returns the dict directly.

### Options

```python
@tool(name="custom_name", approval_required=True, timeout_seconds=60)
def dangerous_action(target: str) -> dict:
    """Do something that requires human approval."""
    return {"done": True}
```

| Parameter | Default | Description |
|---|---|---|
| `name` | function name | Override the tool name |
| `approval_required` | `False` | Insert a wait task for human approval before execution |
| `timeout_seconds` | `None` | Maximum execution time |

### ToolContext — shared state and dependencies

Add a `context: ToolContext` parameter to access execution context and shared state:

```python
from agentspan.agents import tool, ToolContext

@tool
def query_database(query: str, context: ToolContext) -> dict:
    """Run a database query."""
    db = context.dependencies["db"]
    user_id = context.dependencies["user_id"]
    return db.execute(query, user=user_id)

@tool
def add_item(item: str, context: ToolContext) -> str:
    """Add an item to the shared list."""
    items = context.state.get("items", [])
    items.append(item)
    context.state["items"] = items
    return f"Added '{item}'. List has {len(items)} items."
```

`ToolContext` fields:

| Field | Type | Description |
|---|---|---|
| `workflow_id` | `str` | Execution ID |
| `session_id` | `str` | Session ID |
| `agent_name` | `str` | Name of the executing agent |
| `dependencies` | `Dict` | Dependencies injected via `Agent(dependencies=...)` |
| `state` | `Dict` | Mutable shared state across tool calls in the same execution |
| `metadata` | `Dict` | Metadata from the agent |

The `context` parameter is excluded from the tool's JSON schema — the LLM never sees it.

Pass dependencies at agent creation:

```python
agent = Agent(
    name="bot",
    model="openai/gpt-4o",
    tools=[query_database],
    dependencies={"db": my_database, "user_id": "u-123"},
)
```

## `http_tool()` — HTTP Endpoints

Define a single HTTP endpoint as a tool. Executes entirely server-side — no worker process needed:

```python
from agentspan.agents import http_tool

weather_api = http_tool(
    name="get_weather",
    description="Get weather for a city",
    url="https://api.weather.com/v1/current",
    method="GET",
    headers={"Authorization": "Bearer token"},
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)

agent = Agent(name="assistant", model="openai/gpt-4o", tools=[weather_api])
```

## `api_tool()` — OpenAPI Auto-Discovery

Point to any OpenAPI, Swagger, or Postman spec. All endpoints are auto-discovered and exposed as tools. The LLM filters to the most relevant ones at runtime:

```python
from agentspan.agents import api_tool

stripe = api_tool(
    url="https://api.stripe.com/openapi.json",
    headers={"Authorization": "Bearer ${STRIPE_KEY}"},
    credentials=["STRIPE_KEY"],
    max_tools=20,   # LLM auto-filters 300+ ops to top 20 most relevant
)

agent = Agent(
    name="billing_assistant",
    model="openai/gpt-4o",
    tools=[stripe],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Create a Stripe customer for alice@example.com")
    result.print_result()
```

| Parameter | Description |
|---|---|
| `url` | URL to an OpenAPI/Swagger JSON spec, or a Postman collection |
| `headers` | HTTP headers sent with every request (use `${CRED_KEY}` for credentials) |
| `credentials` | List of credential keys to inject (see below) |
| `max_tools` | Maximum tools to expose to the LLM (default: all) |

## `mcp_tool()` — MCP Servers

Connect to an MCP server. Tools are auto-discovered at runtime. Executes server-side:

```python
from agentspan.agents import mcp_tool

github = mcp_tool(
    server_url="http://localhost:6767/mcp",
    name="github",
    description="GitHub operations",
)

agent = Agent(name="dev_assistant", model="openai/gpt-4o", tools=[github])
```

## Credential Management

Store secrets on the server once. Tools resolve them automatically at runtime — no `.env` files, no hardcoded keys, no secrets in git.

**Step 1: Store credentials**

```bash
agentspan credentials set GITHUB_TOKEN ghp_xxxxxxxxxxxx
agentspan credentials set SEARCH_API_KEY xxx-your-key
```

Credentials are encrypted at rest (AES-256-GCM).

**Step 2: Declare which credentials a tool needs**

```python
from agentspan.agents import tool, get_credential

# Option A: isolated subprocess (credentials available as env vars)
@tool(credentials=["GITHUB_TOKEN"])
def list_repos(username: str) -> dict:
    """List GitHub repos."""
    import os
    token = os.environ["GITHUB_TOKEN"]   # Auto-injected
    return {"repos": ["repo1", "repo2"]}

# Option B: in-process (use get_credential)
@tool(isolated=False, credentials=["SEARCH_API_KEY"])
def search(query: str) -> dict:
    """Search using API key."""
    key = get_credential("SEARCH_API_KEY")   # Resolved from server
    return {"results": ["result1"]}
```

**With HTTP and MCP tools:**

```python
# HTTP tool: server substitutes ${KEY} in headers at runtime
api = http_tool(
    name="weather_api", description="Get weather",
    url="https://api.weather.com/v1/current",
    headers={"Authorization": "Bearer ${WEATHER_KEY}"},
    credentials=["WEATHER_KEY"],
)

# MCP tool: credentials passed to MCP server connection
github = mcp_tool(
    server_url="http://localhost:3001/mcp",
    credentials=["GITHUB_TOKEN"],
)
```

**Agent-level credentials (shared with all tools):**

```python
agent = Agent(
    name="github_helper",
    model="openai/gpt-4o",
    tools=[list_repos, search],
    credentials=["GITHUB_TOKEN"],
)
```

## Code Execution

Agents can execute code in a sandboxed environment:

```python
from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.code_executor import DockerCodeExecutor

executor = DockerCodeExecutor(image="python:3.12-slim", timeout=30)

agent = Agent(
    name="coder",
    model="openai/gpt-4o",
    tools=[executor.as_tool()],
    instructions="Write and execute Python code to solve problems.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Calculate the first 20 Fibonacci numbers.")
    result.print_result()
```

Four built-in execution environments:

| Executor | Use case |
|---|---|
| `DockerCodeExecutor` | Docker container (isolated, recommended for production) |
| `LocalCodeExecutor` | Local subprocess (fast, no isolation) |
| `JupyterCodeExecutor` | Jupyter kernel (stateful, good for data science) |
| `ServerlessCodeExecutor` | Cloud function (scales to zero) |

## Human Approval

Mark any tool to require human approval before it runs:

```python
@tool(approval_required=True)
def delete_production_data(table: str) -> dict:
    """Delete data from a production table. Requires approval."""
    return {"deleted": True, "table": table}
```

The execution pauses when the LLM calls this tool. Use `handle.approve()` or `handle.reject(reason)` to resume. See [Human-in-the-Loop examples](/docs/examples/human-in-the-loop).

## Circuit Breaker

Tools that fail 3 consecutive times are automatically disabled. The LLM is told to try a different approach. On a successful call, the error counter resets.

## Mixing Tool Types

Agents can use all tool types together:

```python
agent = Agent(
    name="assistant",
    model="openai/gpt-4o",
    tools=[
        get_weather,       # @tool Python function
        weather_api,       # http_tool
        stripe,            # api_tool (OpenAPI)
        github,            # mcp_tool
    ],
)
```
