---
title: Crash and resume
description: How Agentspan keeps agents running through process crashes, restarts, and reconnects
---

# Crash and resume

**The problem:** Most agent frameworks run the agent loop inside your process. If your process crashes — or you deploy a new version, restart a pod, or lose a network connection — the agent's in-flight work is gone.

**How Agentspan solves it:** The agent loop runs on the Agentspan server, not in your process. Your worker registers tools and polls for tasks. The agent state lives on the server. Your process can die and restart freely.

---

## How it works

```
Your process                Agentspan server
──────────────             ────────────────────────────
start(agent, prompt)  ──►  Creates workflow, starts agent loop
                           LLM call → tool scheduled → worker executes
Worker polls tasks ◄──────  Dispatch: run_my_tool(input)
Worker returns result ────► Continue agent loop
                           ...
process crashes            Agent loop continues on server
                           Next tool call is scheduled
Worker restarts ◄──────    Task is still queued, picked up on reconnect
                           Agent loop resumes from where it was
```

The Conductor engine underlying Agentspan has durable execution built in — the same engine that powers workflows at Netflix, LinkedIn, and Tesla.

---

## Try it: two-script walkthrough

This example uses two scripts to show the full crash-resume cycle. Run them in order.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Environment variables set:
    
    ```bash
    export OPENAI_API_KEY=sk-...   # or ANTHROPIC_API_KEY if using Anthropic
    ```

### Step 1 — Start the agent (`start.py`)

Run this script. It starts the agent, prints the execution ID, checks status, then exits. The process ending is intentional — this simulates the crash.

```python
# start.py
from agentspan.agents import Agent, tool, start

@tool
def analyze_chunk(chunk_id: int, data: str) -> dict:
    """Analyze a data chunk and return metrics."""
    return {"chunk_id": chunk_id, "processed": True, "metrics": {"count": len(data)}}

@tool
def aggregate_results(results: list) -> dict:
    """Aggregate metrics from all chunks into a final report."""
    return {"total_chunks": len(results), "summary": "Analysis complete"}

agent = Agent(
    name="data_analysis_agent",
    model="openai/gpt-4o-mini",
    tools=[analyze_chunk, aggregate_results],
    instructions="""Analyze data in chunks using analyze_chunk, then aggregate with aggregate_results.
    Process each chunk sequentially. Report progress as you go.""",
)

handle = start(agent, "Analyze customer feedback dataset: chunk 1, chunk 2, chunk 3")
print(f"execution_id: {handle.execution_id}")
# execution_id: <execution-id>   ← copy this

status = handle.get_status()
print(f"Status: {status.status}")   # RUNNING
# Script exits here — workflow keeps running on the server
```

### Step 2 — Reconnect (`reconnect.py`)

Paste the execution ID from Step 1 and run this script. It re-registers the tool workers, reconnects to the in-flight workflow, and streams the remaining events to completion.

```python
# reconnect.py
from agentspan.agents import Agent, tool, AgentRuntime, AgentHandle

# Same agent and tools as start.py — workers need to be registered to handle tool calls
@tool
def analyze_chunk(chunk_id: int, data: str) -> dict:
    """Analyze a data chunk."""
    return {"chunk_id": chunk_id, "processed": True, "metrics": {"count": len(data)}}

@tool
def aggregate_results(results: list) -> dict:
    """Aggregate metrics from all chunks into a final report."""
    return {"total_chunks": len(results), "summary": "Analysis complete"}

agent = Agent(
    name="data_analysis_agent",
    model="openai/gpt-4o-mini",
    tools=[analyze_chunk, aggregate_results],
    instructions="...",
)

EXECUTION_ID = "<execution-id>"  # paste from Step 1

with AgentRuntime() as runtime:
    # Register workers first — the server may already have tool tasks queued
    runtime.serve(agent, blocking=False)

    handle = AgentHandle(execution_id=EXECUTION_ID, runtime=runtime)
    print(f"Reconnected. Status: {handle.get_status().status}")  # RUNNING

    # Stream remaining events to completion
    for event in handle.stream():
        if event.type == "tool_call":
            print(f"→ {event.tool_name}({event.args})")
        elif event.type == "tool_result":
            print(f"← {event.tool_name}: {event.result}")
        elif event.type == "done":
            print(f"\nResult: {event.output['result']}")
            break

# The agent never noticed the process crashed.
# It was running on the server the whole time.
```

---

## Reconnecting after a crash

The execution ID is all you need to reconnect from any process, any machine.

**If your agent has no `@tool` functions** (LLM-only agent), reconnecting is straightforward:

```python
from agentspan.agents import AgentRuntime, AgentHandle

with AgentRuntime() as runtime:
    handle = AgentHandle(execution_id="<execution-id>", runtime=runtime)
    result = handle.stream().get_result()
    print(result.output["result"])  # output is a dict: {"result": "...", "finishReason": "STOP", ...}
```

**If your agent has `@tool` functions**, the reconnecting process must also register those workers — otherwise the workflow will hang waiting for a worker that never arrives. See Step 2 above for the full pattern.

---

## Checking status from the CLI

```bash
agentspan agent status <execution-id>
```

---

## Production pattern: separate worker from invoker

In production, keep the worker process (which handles tool calls) separate from the invoker (which starts runs):

```python
# worker.py — runs continuously, handles tool execution
from agentspan.agents import Agent, tool, AgentRuntime

@tool
def analyze_chunk(chunk_id: int, data: str) -> dict:
    """Analyze a data chunk and return metrics."""
    return {"chunk_id": chunk_id, "processed": True}

agent = Agent(
    name="data_analysis_agent",
    model="openai/gpt-4o-mini",
    tools=[analyze_chunk],
    instructions="...",
)

with AgentRuntime() as runtime:
    runtime.serve(agent)  # registers workers and blocks
```

```python
# invoker.py — runs once per job (REST endpoint, cron, CLI, etc.)
from agentspan.agents import Agent, tool, start

@tool
def analyze_chunk(chunk_id: int, data: str) -> dict:
    """Analyze a data chunk and return metrics."""
    return {"chunk_id": chunk_id, "processed": True}

agent = Agent(
    name="data_analysis_agent",
    model="openai/gpt-4o-mini",
    tools=[analyze_chunk],
    instructions="...",
)

handle = start(agent, "Analyze the dataset")
print(f"Job ID: {handle.execution_id}")
# Store this ID — use it to reconnect or check status later
```

---

## Idempotency: never re-process completed work

Use `get_status()` to skip work that's already done before starting a new run:

```python
from agentspan.agents import Agent, start, AgentRuntime, AgentHandle

def ensure_analysis_running(execution_id: str | None, agent, prompt: str):
    """Start a new run or reconnect to an existing one."""
    if execution_id:
        with AgentRuntime() as runtime:
            handle = AgentHandle(execution_id=execution_id, runtime=runtime)
            status = handle.get_status()
            if status.is_complete:
                print("Already done")
                return handle
            if status.is_running or status.is_waiting:
                print(f"Still running: {status.status}")
                return handle
    # Start fresh
    return start(agent, prompt)
```

---

## Full stream with reconnect

Stream events from a run — whether it's new or already in progress:

```python
from agentspan.agents import Agent, tool, AgentRuntime, AgentHandle

# Re-define (or import) agent and tools so workers can be registered
@tool
def analyze_chunk(chunk_id: int, data: str) -> dict:
    """Analyze a data chunk and return metrics."""
    return {"chunk_id": chunk_id, "processed": True}

agent = Agent(
    name="data_analysis_agent",
    model="openai/gpt-4o-mini",
    tools=[analyze_chunk],
    instructions="...",
)

with AgentRuntime() as runtime:
    runtime.serve(agent, blocking=False)
    handle = AgentHandle(execution_id="<execution-id>", runtime=runtime)

    for event in handle.stream():
        if event.type == "tool_call":
            print(f"→ {event.tool_name}({event.args})")
        elif event.type == "tool_result":
            print(f"← {event.tool_name}: {event.result}")
        elif event.type == "done":
            print(f"\nResult: {event.output['result']}")  # output is a dict: {"result": "...", "finishReason": "STOP", ...}
            break
```
