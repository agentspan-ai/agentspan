# Getting started

## Under 30 seconds

The package is named `conductor-agent-sdk` (see `pyproject.toml`). This project uses `uv`.

```bash
uv add conductor-agent-sdk
```

Point the SDK at a running Agentspan server (defaults to `http://localhost:6767/api`):

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
export OPENAI_API_KEY=sk-...        # whichever provider your model uses
```

Write `hello.py`:

```python
from conductor.ai.agents import Agent, AgentRuntime

agent = Agent(
    name="greeter",
    model="openai/gpt-4o-mini",
    instructions="You are a friendly assistant. Keep responses brief.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Say hello and tell me a fun fact about Python.")
    print(result.output)
```

Run it:

```bash
uv run python hello.py
```

That is the whole loop: define an `Agent`, open an `AgentRuntime`, call `run`. The
runtime compiles the agent to a workflow, starts it, and blocks until it returns an
[`AgentResult`](api-reference.md#agentresult). `result.print_result()` pretty-prints
the output if you prefer.

## Environment variables

`AgentConfig.from_env()` reads these (all optional — defaults shown):

| Variable | Default | Purpose |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server base URL |
| `AGENTSPAN_API_KEY` | — | API key auth |
| `AGENTSPAN_AUTH_KEY` | — | Key/secret auth — key |
| `AGENTSPAN_AUTH_SECRET` | — | Key/secret auth — secret |
| `AGENTSPAN_LLM_RETRY_COUNT` | `3` | LLM call retries |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_WORKER_THREADS` | `1` | Worker thread count |
| `AGENTSPAN_AUTO_START_WORKERS` | `true` | Auto-start local tool workers |
| `AGENTSPAN_AUTO_START_SERVER` | `true` | Auto-start a local server if none is reachable |
| `AGENTSPAN_DAEMON_WORKERS` | `true` | Run workers as daemon threads |
| `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | `false` | Auto-register provider integrations |
| `AGENTSPAN_STREAMING_ENABLED` | `true` | Enable SSE streaming |
| `AGENTSPAN_SECRET_STRICT_MODE` | `false` | Fail hard on missing secrets |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | Log level |

The model string is `"provider/model"`, e.g. `openai/gpt-4o-mini`,
`anthropic/claude-sonnet-4-20250514`, `google_gemini/gemini-2.0-flash`. Set the
matching provider API key in the environment of whoever runs the agent's workers.

## What `model` looks like

```python
Agent(name="a", model="openai/gpt-4o")              # OpenAI
Agent(name="b", model="anthropic/claude-sonnet-4-20250514")
Agent(name="c", model="google_gemini/gemini-2.0-flash")
```

## Next

- Add tools, sub-agents, and human-in-the-loop: [Writing agents](writing-agents.md).
- Deploy once and serve workers separately for production: [Advanced](advanced.md).
