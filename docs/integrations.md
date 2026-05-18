---
title: Framework Integrations
description: Use Agentspan with LangGraph, the OpenAI Agents SDK, Google ADK, or any framework. Pass your existing agent to runtime.run() — one line, no rewrites.
---

# Framework Integrations

Agentspan works with the frameworks you already use. Pass your existing agent directly to `runtime.run()` — definitions, tools, and routing logic stay exactly as written. You get crash recovery, durable human-in-the-loop, and full execution history without changing a single node or handoff.

```python
from agentspan.agents import AgentRuntime

with AgentRuntime() as runtime:
    result = runtime.run(your_existing_agent, "your prompt")
```

`your_existing_agent` can be a LangGraph compiled graph, an OpenAI Agents SDK `Agent`, a Google ADK pipeline, or a native Agentspan `Agent`. The API is the same.

---

## Supported frameworks

### LangGraph

Pass a compiled `StateGraph` or any graph produced by `create_react_agent`:

```python
from langgraph.prebuilt import create_react_agent
from agentspan.agents import AgentRuntime

graph = create_react_agent(model="openai/gpt-4o", tools=[search, calculator])

with AgentRuntime() as runtime:
    result = runtime.run(graph, "Research the history of the Eiffel Tower")
    print(result.workflow_id)
```

**Note:** Do not pass a `checkpointer` when wrapping with AgentRuntime — Agentspan manages execution state server-side and the two checkpointing models conflict. LangSmith observability is fully compatible and unaffected.

→ [Full LangGraph example — code review bot](/docs/examples/langgraph)

---

### OpenAI Agents SDK

Pass an `Agent` from the `agents` package directly:

```python
from agents import Agent as OAIAgent, WebSearchTool
from agentspan.agents import AgentRuntime

oai_agent = OAIAgent(
    name="support_agent",
    instructions="You are a helpful customer support agent.",
    tools=[WebSearchTool()],
)

with AgentRuntime() as runtime:
    result = runtime.run(oai_agent, "How do I reset my password?")
    print(result.output["result"])
```

Agent definitions, handoffs, and tool registrations stay exactly as written.

→ [Full OpenAI Agents SDK example — support agent](/docs/examples/openai-agents-sdk)

---

### Google ADK

Pass any ADK pipeline (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, or a custom `BaseAgent`):

```python
from google.adk.agents import SequentialAgent, LlmAgent
from agentspan.agents import AgentRuntime

researcher = LlmAgent(name="researcher", model="gemini-2.0-flash", ...)
writer = LlmAgent(name="writer", model="gemini-2.0-flash", ...)
pipeline = SequentialAgent(name="pipeline", sub_agents=[researcher, writer])

with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "Research and summarize quantum computing trends")
    print(result.output["result"])
```

→ [Full Google ADK example — research assistant](/docs/examples/google-adk)

---

## What Agentspan adds to any framework

| Capability | Without Agentspan | With Agentspan |
|---|---|---|
| Process crash mid-run | Entire run lost | Resumes from last completed step |
| Human approval pause | State held in memory | Paused server-side, survives restarts |
| Execution history | None | Every run stored with inputs, outputs, token usage |
| Long-running agents | Risk of timeout or OOM | Runs detached from your process |
| Observability | Framework-specific | Unified across all frameworks |

---

## Tool locality

Regardless of which framework you use, tools in Agentspan run in one of two places:

| Tool type | Where it runs | What you provide |
|---|---|---|
| `@tool` (Python function) | **Your worker process** | The function code |
| `http_tool()` | **Agentspan server** | A URL and optional headers |
| `api_tool()` | **Agentspan server** | An OpenAPI/Swagger spec URL |
| `mcp_tool()` | **Agentspan server** | An MCP server URL |

When you wrap a LangGraph graph or OpenAI SDK agent with `AgentRuntime`, its tool functions become worker-executed tasks. Server-side tools (`http_tool`, `api_tool`, `mcp_tool`) run on the server regardless of framework.

See [Tools](/docs/concepts/tools) for details.

---

## Native Agentspan agents

If you're not using an existing framework, define agents natively:

```python
from agentspan.agents import Agent, tool, AgentRuntime

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

agent = Agent(
    name="researcher",
    model="openai/gpt-4o",
    tools=[search_web],
    instructions="Research topics thoroughly.",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "What is quantum entanglement?")
    result.print_result()
```

→ [Quickstart](/docs/quickstart) · [Agents concept](/docs/concepts/agents) · [Tools concept](/docs/concepts/tools)
