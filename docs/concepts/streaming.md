---
title: Streaming
description: stream(), stream_async(), AgentEvent types, and streaming with human-in-the-loop
---

# Streaming

Stream events from an agent execution as they happen — tool calls, thinking steps, handoffs, and the final output.

## Basic Streaming

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="writer", model="openai/gpt-4o")

with AgentRuntime() as runtime:
    for event in runtime.stream(agent, "Write a haiku about Python"):
        match event.type:
            case "thinking":        print(f"Thinking: {event.content}")
            case "tool_call":       print(f"Calling {event.tool_name}({event.args})")
            case "tool_result":     print(f"Result: {event.result}")
            case "handoff":         print(f"Delegating to {event.target}")
            case "waiting":         print("Waiting for human approval...")
            case "guardrail_pass":  print(f"Guardrail passed: {event.guardrail_name}")
            case "guardrail_fail":  print(f"Guardrail failed: {event.guardrail_name}")
            case "message":         print(f"Message: {event.content}")
            case "error":           print(f"Error: {event.content}")
            case "done":            print(f"\nFinal: {event.output}")
```

## Module-level stream()

```python
from agentspan.agents import Agent, stream

agent = Agent(name="writer", model="openai/gpt-4o")
for event in stream(agent, "Write a poem"):
    if event.type == "done":
        print(event.output)
```

## Async Streaming

```python
from agentspan.agents import Agent, AgentRuntime

agent = Agent(name="writer", model="openai/gpt-4o")

async def main():
    with AgentRuntime() as runtime:
        async for event in runtime.stream_async(agent, "Write a haiku"):
            if event.type == "done":
                print(event.output)
```

## AgentEvent Fields

| Field | Type | Description |
|---|---|---|
| `type` | `str` | Event type (see below) |
| `content` | `Optional[str]` | Text content (thinking, message, error) |
| `tool_name` | `Optional[str]` | Tool name (tool_call, tool_result) |
| `args` | `Optional[Dict]` | Tool arguments (tool_call) |
| `result` | `Any` | Tool result (tool_result) |
| `target` | `Optional[str]` | Agent name for handoff events |
| `output` | `Any` | Final output (done event only) |
| `workflow_id` | `str` | Execution ID |
| `guardrail_name` | `Optional[str]` | Guardrail name (guardrail_pass, guardrail_fail) |

## Event Types

| Type | When |
|---|---|
| `thinking` | Agent internal reasoning step |
| `tool_call` | LLM is calling a tool |
| `tool_result` | Tool returned a result |
| `handoff` | Control passes to a sub-agent |
| `waiting` | Agent paused for human approval |
| `guardrail_pass` | A guardrail passed |
| `guardrail_fail` | A guardrail failed |
| `message` | Agent sent an intermediate message |
| `error` | An error occurred |
| `done` | Agent completed — `event.output` has the final result |

## Streaming with Tools

```python
from agentspan.agents import Agent, AgentRuntime, tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

agent = Agent(
    name="researcher",
    model="openai/gpt-4o",
    tools=[search_web],
)

with AgentRuntime() as runtime:
    for event in runtime.stream(agent, "What is agentspan?"):
        match event.type:
            case "tool_call":
                print(f"  → Calling {event.tool_name}({event.args})")
            case "tool_result":
                print(f"  ← {event.result}")
            case "done":
                print(f"\nAnswer: {event.output}")
```

## Streaming with Human-in-the-Loop

When an agent is waiting for approval, the `waiting` event fires. Handle it from a separate process using the execution ID:

```python
from agentspan.agents import Agent, AgentRuntime, AgentHandle, tool

@tool(approval_required=True)
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email. Requires approval."""
    return {"sent": True}

agent = Agent(name="emailer", model="openai/gpt-4o", tools=[send_email])

with AgentRuntime() as runtime:
    workflow_id = None
    for event in runtime.stream(agent, "Send a welcome email to alice@example.com"):
        if event.type == "waiting":
            workflow_id = event.workflow_id
            print(f"Agent waiting for approval. Execution ID: {workflow_id}")
            break
        elif event.type == "done":
            print(f"Done: {event.output}")

# Later, from anywhere — approve or reject:
if workflow_id:
    runtime2 = AgentRuntime()
    runtime2.serve(agent, blocking=False)   # start workers before reconnecting
    handle = AgentHandle(workflow_id=workflow_id, runtime=runtime2)
    handle.approve()
```

## Get Result from Stream

To get the final `AgentResult` after streaming:

```python
from agentspan.agents import Agent, AgentRuntime, start

agent = Agent(name="writer", model="openai/gpt-4o")

with AgentRuntime() as runtime:
    handle = runtime.start(agent, "Write a report")
    result = handle.stream().get_result()   # Wait for completion
    print(result.output)
```

## Filtering Events

```python
with AgentRuntime() as runtime:
    tool_events = [
        event
        for event in runtime.stream(agent, "Research AI agents")
        if event.type in ("tool_call", "tool_result")
    ]
```
