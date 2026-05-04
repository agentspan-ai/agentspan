---
title: Google ADK — research assistant
description: Multi-agent research assistant built with Google ADK and Gemini, wrapped with Agentspan
---

# Google ADK — Research Assistant

This example shows how to wrap an existing Google ADK multi-agent pipeline with Agentspan. A sequential pipeline chains a web researcher, a data analyst, and a writer — with crash recovery and full step visibility added by replacing the runner setup with one line.

## What Agentspan adds to Google ADK

Google ADK handles your agent pipeline — `LlmAgent`, `SequentialAgent`, tools, and instructions. Agentspan adds a production execution layer without changing any of that:

- **Crash recovery**: Pipeline execution runs on the Agentspan server; a process restart resumes from the current sub-agent
- **No session management**: Agentspan replaces `InMemorySessionService` and `Runner` setup; your pipeline definition is unchanged
- **Per-agent step visibility**: Every tool call and sub-agent handoff is logged and browsable in the UI at `http://localhost:6767`
- **Execution history**: Every research run is stored with inputs, outputs, and timing

Your agent definitions, sub-agent structure, tools, and instructions stay exactly as written.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Additional dependencies: `pip install google-adk httpx markdownify`
    - Environment variables set:
    
    ```bash
    export GEMINI_API_KEY=...
    ```

---

## Before: plain Google ADK

Standard Google ADK code. Runs fine locally but all execution state lives in `InMemorySessionService` — a process crash loses everything.

```python
import asyncio
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import google_search, FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# ── Tools ────────────────────────────────────────────────────────────────────

def fetch_page(url: str) -> str:
    """Fetch and return readable text content from a URL."""
    import httpx
    from markdownify import markdownify
    resp = httpx.get(url, timeout=10, follow_redirects=True)
    return markdownify(resp.text)[:6000]

def run_python(code: str) -> str:
    """Execute Python code and return stdout. Use for data analysis."""
    import subprocess
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout or result.stderr

fetch_tool = FunctionTool(func=fetch_page)
python_tool = FunctionTool(func=run_python)

# ── Sub-agents ────────────────────────────────────────────────────────────────

researcher = LlmAgent(
    name="researcher",
    model="gemini-2.0-flash",
    description="Web researcher. Searches and reads sources.",
    instruction="""You are a research specialist. Given a topic:
1. Run 3–5 targeted Google searches
2. Fetch and read the most informative pages
3. Extract key facts, statistics, and direct quotes with source URLs
4. Return a structured research brief — facts only, no prose""",
    tools=[google_search, fetch_tool],
)

analyst = LlmAgent(
    name="analyst",
    model="gemini-2.0-flash",
    description="Data analyst. Runs calculations and finds patterns.",
    instruction="""You are a data analyst. Given research notes:
1. Identify any numerical claims or datasets worth verifying
2. Run Python calculations to check figures or derive insights
3. Summarize your findings with the code you ran
Return your analysis as structured notes.""",
    tools=[python_tool],
)

writer = LlmAgent(
    name="writer",
    model="gemini-2.5-pro",  # stronger model for the final output
    description="Technical writer. Produces the final report.",
    instruction="""You are a technical writer. Given research and analysis:
1. Write a clear, well-structured report with an executive summary
2. Use specific numbers and quotes — never vague claims
3. Cite all sources inline
4. End with a 'Key Takeaways' section (3–5 bullet points)""",
)

# ── Sequential pipeline ───────────────────────────────────────────────────────

pipeline = SequentialAgent(
    name="research_pipeline",
    description="Full research pipeline: search → analyse → write",
    sub_agents=[researcher, analyst, writer],
)

# ── Run (plain ADK — no durability) ──────────────────────────────────────────

APP_NAME = "research_assistant"

async def run_research(topic: str) -> str:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="user1",
        session_id="session1",
    )
    runner = Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )
    events = runner.run_async(
        user_id="user1",
        session_id="session1",
        new_message=Content(role="user", parts=[Part(text=topic)]),
    )
    final_response = ""
    async for event in events:
        if event.is_final_response():
            final_response = event.content.parts[0].text
    return final_response

result = asyncio.run(run_research("The current state of durable execution for AI agents"))
print(result)
```

---

## After: wrapped with Agentspan

Three things change from the plain ADK version: `LlmAgent` → `Agent`, model strings use the `google_gemini/` provider prefix, and the runner setup is replaced with `runtime.run()`. Tools are passed as plain functions — no `FunctionTool` wrapper needed.

```python
from google.adk.agents import Agent, SequentialAgent
from agentspan.agents import AgentRuntime

# ── Tools (unchanged — no FunctionTool wrapper needed) ───────────────────────

def fetch_page(url: str) -> str:
    """Fetch and return readable text content from a URL."""
    import httpx
    from markdownify import markdownify
    resp = httpx.get(url, timeout=10, follow_redirects=True)
    return markdownify(resp.text)[:6000]

def run_python(code: str) -> str:
    """Execute Python code and return stdout. Use for data analysis."""
    import subprocess
    result = subprocess.run(
        ["python", "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout or result.stderr

def search_web(query: str) -> dict:
    """Search the web and return a summary of results for the query."""
    return {"query": query, "results": f"Top results for: {query}"}

# ── Sub-agents ────────────────────────────────────────────────────────────────

researcher = Agent(
    name="researcher",
    model="google_gemini/gemini-2.0-flash",
    description="Web researcher. Searches and reads sources.",
    instruction="""You are a research specialist. Given a topic:
1. Run 3–5 targeted Google searches
2. Fetch and read the most informative pages
3. Extract key facts, statistics, and direct quotes with source URLs
4. Return a structured research brief — facts only, no prose""",
    tools=[search_web, fetch_page],
)

analyst = Agent(
    name="analyst",
    model="google_gemini/gemini-2.0-flash",
    description="Data analyst. Runs calculations and finds patterns.",
    instruction="""You are a data analyst. Given research notes:
1. Identify any numerical claims or datasets worth verifying
2. Run Python calculations to check figures or derive insights
3. Summarize your findings with the code you ran
Return your analysis as structured notes.""",
    tools=[run_python],
)

writer = Agent(
    name="writer",
    model="google_gemini/gemini-2.5-pro",  # stronger model for the final output
    description="Technical writer. Produces the final report.",
    instruction="""You are a technical writer. Given research and analysis:
1. Write a clear, well-structured report with an executive summary
2. Use specific numbers and quotes — never vague claims
3. Cite all sources inline
4. End with a 'Key Takeaways' section (3–5 bullet points)""",
)

# ── Sequential pipeline ───────────────────────────────────────────────────────

pipeline = SequentialAgent(
    name="research_pipeline",
    description="Full research pipeline: search → analyse → write",
    sub_agents=[researcher, analyst, writer],
)

# was: the whole runner setup above (session_service, Runner, run_async, etc.)
with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "The current state of durable execution for AI agents")

print(result.output)
print(f"Run ID: {result.execution_id}")
```

`runtime.run()` registers the full pipeline execution — including every sub-agent step and tool call — as a single managed run on the Agentspan server.

---

## Run it

Save all the code above into a single file called `research_assistant.py`, then run:

```bash
python research_assistant.py
```

---

## What this demonstrates

```
topic → [research_pipeline] → [researcher] → [analyst] → [writer] → final report
```

**Sequential pipeline, Agentspan runtime**: The sub-agent chain (`researcher → analyst → writer`) runs exactly as defined. Replace the runner setup with `runtime.run` and the entire pipeline runs on the Agentspan server.

**Per-agent step visibility**: Every tool call and sub-agent handoff is a logged step. Open `http://localhost:6767` to see which agent was active at each step, what tools it called, and what it produced.

**Crash recovery**: If your process dies mid-pipeline (network timeout, OOM, deploy restart), Agentspan resumes from the current sub-agent when a new worker connects. The research run isn't dropped.

**Run history**: Every execution is stored with inputs, outputs, token usage, and timing.

---

## Example modifications

### Run asynchronously

```python
import asyncio
from agentspan.agents import run_async

async def run_research(topic: str) -> str:
    result = await run_async(pipeline, topic)
    return result.output

asyncio.run(run_research("The current state of durable execution for AI agents"))
```

### Fire-and-forget for long research jobs

Use `start` to submit a job and return immediately. Useful when research runs are slow and you don't want to block.

```python
from agentspan.agents import start

# Launch and return immediately — pipeline runs in the background on the server
handle = start(pipeline, topic)
print(f"Running: {handle.execution_id}")

# Check status
status = handle.get_status()
print(status.status)  # "RUNNING" | "COMPLETED" | "FAILED"

# Or wait for result
result = handle.stream().get_result()
print(result.output)
```

### Run multiple topics concurrently

`start` works in a loop — each call submits immediately without waiting for the previous one to finish.

```python
from agentspan.agents import start

topics = [
    "Durable execution frameworks for AI agents",
    "LangGraph vs OpenAI Agents SDK comparison 2026",
    "Serverless vs container deployments for AI agent workloads",
]

# All three run concurrently on the Agentspan server
handles = [start(pipeline, t) for t in topics]
results = [h.stream().get_result() for h in handles]

for r in results:
    print(str(r.output)[:200], "\n---")
```

### Stream sub-agent progress

```python
from agentspan.agents import stream

for event in stream(pipeline, topic):
    if event.type == "handoff":
        print(f"\n── {event.target} ──")
    elif event.type == "tool_call":
        print(f"  → {event.tool_name}({event.args})")
    elif event.type == "done":
        print(f"\n{event.output}")
```

---

## Testing

Use `mock_run` to test the pipeline without a live server or real API calls. Supply the expected sequence of sub-agent handoffs and tool calls; `mock_run` drives the pipeline through them and returns an `AgentResult` you can assert against.

```python
from agentspan.agents.testing import mock_run, MockEvent, expect

result = mock_run(
    pipeline,
    "The current state of durable execution for AI agents",
    events=[
        MockEvent.handoff("researcher"),
        MockEvent.tool_call("search_web", {"query": "durable execution AI agents 2026"}),
        MockEvent.tool_result("search_web", "Agentspan, LangGraph, and OpenAI Agents SDK lead..."),
        MockEvent.handoff("analyst"),
        MockEvent.handoff("writer"),
        MockEvent.done("# Final Report\nDurable execution has become..."),
    ]
)

expect(result).completed().used_tool("search_web")
```
