# Agentspan Python SDK

Durable, scalable, observable AI agents. You write plain Python; Agentspan compiles
your agent into a Conductor workflow that runs on a server — with automatic retries,
durable state, human-in-the-loop pauses, streaming, and scheduling.

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="greeter", model="openai/gpt-4o-mini",
              instructions="You are a friendly assistant.")

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Say hello.")
    print(result.output)
```

## Docs

- [Getting started](getting-started.md) — install, env vars, and a running agent in under 30 seconds.
- [Writing agents](writing-agents.md) — the `Agent` class and `@agent`, tools, multi-agent strategies, handoffs, guardrails, termination, callbacks, streaming + HITL, schedules, stateful and instance agents.
- [Framework agents](framework-agents.md) — run agents authored in the OpenAI Agents SDK, LangChain, LangGraph, or the Claude Agent SDK.
- [Advanced](advanced.md) — runtime config, the control-plane `AgentClient`, deploy vs serve vs run vs plan, structured output, credentials, plans (`PLAN_EXECUTE`), skills.
- [API reference](api-reference.md) — the public API surface in one place.

## Import surface

Everything public is importable from `agentspan.agents`:

```python
from agentspan.agents import Agent, AgentRuntime, tool, agent
```

A small OpenAI-Agents-compatible shim is also exposed at the top level:

```python
from agentspan import Runner, function_tool   # drop-in for `agents.Runner`
```
