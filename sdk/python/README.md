# Agentspan Python SDK

Python SDK for building and running AI agents on [Conductor](https://github.com/conductor-oss/conductor). Define agents and tools in plain Python, run them durably on Conductor.

- **Python-first** — type-annotated, decorator-based API with no boilerplate
- **Conductor workers** — tool functions run as distributed Conductor tasks via [`conductor-python`](https://github.com/conductor-oss/conductor-python)
- **Same wire format** as the [JS SDK](../typescript) — share agents across languages

---

## Installation

```bash
pip install agentspan
```

Or with `uv`:

```bash
uv add agentspan
```

Requires **Python 3.9+**.

---

## Quick start

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city."""
    return {"city": city, "temperature_f": 72, "condition": "Sunny"}

agent = Agent(
    name="weather_agent",
    model="openai/gpt-4o",
    instructions="You are a helpful weather assistant.",
    tools=[get_weather],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in SF?")
    result.print_result()
```

---

## Configuration

Set environment variables (or create a `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:8080/api` | Conductor server URL |
| `AGENTSPAN_AUTH_KEY` | — | Auth key (Orkes Cloud only) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret (Orkes Cloud only) |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARN` / `ERROR` |
| `AGENT_LLM_MODEL` | — | Model in `provider/model` format, e.g. `openai/gpt-4o` |

---

## API reference

### `@tool`

Wraps a function as an agent tool. Type hints are used to generate the JSON schema automatically.

```python
from agentspan.agents import tool

@tool
def add(x: int, y: int) -> dict:
    """Add two numbers."""
    return {"sum": x + y}

# With options:
@tool(name="custom_name", approval_required=True, timeout_seconds=30)
def sensitive_action(target: str) -> dict:
    """Do something that needs approval."""
    ...
```

#### Server-side tools (no local worker)

```python
from agentspan.agents import http_tool, mcp_tool

# HTTP tool — Conductor calls the endpoint directly
weather_api = http_tool(
    name="get_weather",
    description="Fetch live weather data.",
    url="https://api.weather.example.com/current",
    method="GET",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)

# MCP tool — routes through an MCP server
github_tools = mcp_tool(
    server_url="http://localhost:3001/mcp",
    name="github_mcp",
    description="GitHub tools via MCP.",
)
```

---

### `Agent`

```python
from agentspan.agents import Agent

agent = Agent(
    name="my_agent",           # required — unique name, becomes the workflow name
    model="openai/gpt-4o",     # "provider/model" format
    instructions="You are...", # system prompt (string or callable)
    tools=[my_tool],           # @tool functions, http_tool/mcp_tool defs
    max_turns=25,              # max LLM iterations (default: 25)
    temperature=0,             # optional
    max_tokens=4096,           # optional
)
```

#### Multi-agent

```python
researcher = Agent(name="researcher", model="openai/gpt-4o", tools=[search])
writer     = Agent(name="writer",     model="openai/gpt-4o")

# Handoff — LLM decides which sub-agent to call
coordinator = Agent(
    name="coordinator",
    model="openai/gpt-4o",
    agents=[researcher, writer],
    strategy="handoff",
)

# Sequential pipeline — output of each step feeds the next
pipeline = researcher >> writer

# Parallel — all sub-agents run concurrently
panel = Agent(
    name="panel",
    agents=[researcher, writer],
    strategy="parallel",
)
```

---

### `AgentRuntime`

```python
from agentspan.agents import AgentRuntime

runtime = AgentRuntime(
    server_url="http://localhost:8080",  # auto-appends /api if missing
    api_key="...",                       # optional
    api_secret="...",                    # optional
)

# Use as context manager to auto-shutdown workers
with AgentRuntime() as runtime:
    ...
```

#### `runtime.run(agent, prompt)` → `AgentResult`

Blocks until the workflow completes.

```python
result = runtime.run(agent, "What's the weather in SF?")

print(result.output)        # {"result": "The weather in SF is..."}
print(result.status)        # "COMPLETED"
print(result.tool_calls)    # [{"name": ..., "args": ..., "result": ...}, ...]
print(result.is_success)    # True
result.print_result()       # pretty-print to stdout
```

#### `runtime.start(agent, prompt)` → `AgentHandle`

Fire-and-forget — returns a handle immediately.

```python
handle = runtime.start(agent, "Long running task...")

print(handle.workflow_id)

# Poll status
status = handle.get_status()
# status.is_complete, status.is_running, status.is_waiting, status.output, ...

# Human-in-the-loop approval (when status.is_waiting == True)
handle.approve()
handle.reject("Too risky")
```

#### `runtime.stream(agent, prompt)` → `AgentStream`

Stream events as they happen.

```python
for event in runtime.stream(agent, prompt):
    if event.type == "thinking":
        print("thinking:", event.content)
    elif event.type == "tool_call":
        print(f"calling {event.tool_name}(", event.args, ")")
    elif event.type == "tool_result":
        print(f"{event.tool_name} returned", event.result)
    elif event.type == "waiting":
        # approval-required tool is paused — use handle.approve() / handle.reject()
        pass
    elif event.type == "error":
        print("error:", event.content)
    elif event.type == "done":
        print("output:", event.output)
```

#### Async

All methods have `_async` variants:

```python
result = await runtime.run_async(agent, prompt)
handle = await runtime.start_async(agent, prompt)

async for event in runtime.stream_async(agent, prompt):
    ...
```

#### `runtime.plan(agent)` → workflow definition dict

Compile an agent to a Conductor workflow definition without running it.

```python
workflow_def = runtime.plan(agent)
print(json.dumps(workflow_def, indent=2))
```

#### `runtime.shutdown()`

Stop all workers cleanly (called automatically when used as context manager).

```python
runtime.shutdown()
```

---

## Examples

```bash
# Basic agent
uv run python examples/01_basic_agent.py

# Tools
uv run python examples/02a_simple_tools.py

# Streaming events
uv run python examples/11_streaming.py

# Human-in-the-loop
uv run python examples/09_human_in_the_loop.py

# Multi-agent handoff
uv run python examples/05_handoffs.py

# Sequential pipeline
uv run python examples/06_sequential_pipeline.py
```

Set env vars first:

```bash
export AGENTSPAN_SERVER_URL=http://localhost:8080
export AGENT_LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY=...
```

---

## Project structure

```
sdk/python/
├── src/agentspan/
│   ├── agents/
│   │   ├── agent.py          # Agent class + @agent decorator
│   │   ├── tool.py           # @tool, http_tool, mcp_tool, agent_tool, ...
│   │   ├── result.py         # AgentResult, AgentHandle, AgentStream, AgentEvent
│   │   ├── run.py            # Convenience API (run, start, stream, ...)
│   │   ├── guardrail.py      # Guardrail, RegexGuardrail, LLMGuardrail
│   │   ├── memory.py         # ConversationMemory
│   │   ├── termination.py    # TerminationCondition (composable with & |)
│   │   └── runtime/
│   │       ├── runtime.py    # AgentRuntime
│   │       └── config.py     # AgentConfig (env var loading)
│   └── models/
├── examples/                 # 88+ runnable examples
├── tests/
├── pyproject.toml
└── AGENTS.md                 # Full API reference
```
