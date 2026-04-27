---
title: Quickstart
description: Install Agentspan and run your first durable AI agent in under 60 seconds.
---

# Quickstart

Get Agentspan running locally in under 60 seconds.

## Step 1 — Install

```bash
pip install agentspan
```

This installs the Python SDK and the `agentspan` CLI — everything you need as a Python developer.

Verify your setup:

```bash
agentspan doctor
```

> **uv:** `uv pip install agentspan` also works.
>
> **CLI only (no Python SDK):** `npm install -g @agentspan-ai/agentspan` — downloads the binary eagerly at install time, no Python required.

## Step 2 — Set your LLM API key

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

See [Providers](/docs/providers) for all supported models and environment variables.

## Step 3 — Start the server

```bash
agentspan server start
```

On first run, this downloads the Agentspan server JAR (~50 MB) and starts it on `http://localhost:6767`. Subsequent starts use the cached JAR. Open `http://localhost:6767` in your browser to see the visual execution UI.

> **Local default:** The server uses SQLite with WAL mode — no external database needed for local development. Data is stored in `agent-runtime.db` in the working directory.

## Step 4 — Run your first agent

Save this as `hello.py` and run `python hello.py`:

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72°F and sunny in {city}"

agent = Agent(
    name="weatherbot",
    model="openai/gpt-4o", # if you set OPENAI_API_KEY
    # model="anthropic/claude-sonnet-4-6",  # if you set ANTHROPIC_API_KEY
    tools=[get_weather],
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What's the weather in NYC?")
    result.print_result()
```

You should see the answer printed, and the execution visible in the UI at `http://localhost:6767`.

## What just happened?

When you called `runtime.run()`, the SDK:

1. Compiled your `Agent` into a durable execution on the Agentspan server
2. Started a worker process to handle `@tool` function calls
3. Executed the workflow on the server — not in-process
4. Returned the result when complete

**The key difference from other SDKs:** if your process crashes mid-execution, the workflow keeps running on the server. You can reconnect to it by execution ID from any machine.

**Tool locality — what runs where:**
- `@tool` functions run in **your worker process** — full access to your code, libraries, and local state
- `http_tool()`, `api_tool()`, `mcp_tool()` run **server-side** — no code to write, just configure a URL

See [Tools](/docs/concepts/tools) for all tool types.

## Alternative: Using module-level functions

If you prefer not to use the context manager, module-level functions are available. They use a shared singleton runtime under the hood:

```python
from agentspan.agents import Agent, tool, run

@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72°F and sunny in {city}"

agent = Agent(
    name="weatherbot",
    model="openai/gpt-4o", # if you set OPENAI_API_KEY
    # model="anthropic/claude-sonnet-4-6",  # if you set ANTHROPIC_API_KEY
    tools=[get_weather],
)
result = run(agent, "What's the weather in NYC?")
result.print_result()
```

## Next steps

- [Concepts: Agents](/docs/concepts/agents) — all `Agent` constructor parameters
- [Concepts: Tools](/docs/concepts/tools) — `@tool`, `http_tool`, `mcp_tool`, `api_tool`
- [Providers](/docs/providers) — all supported LLM providers and model strings
- [Deployment](/docs/deployment) — local, Docker, and Kubernetes setups
- [Examples](/examples) — 180+ runnable examples
