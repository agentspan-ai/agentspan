---
title: Research pipeline
description: Multi-agent research → write → edit pipeline with crash recovery
---

# Build a Research Pipeline

Use this example to build a multi-agent research pipeline that takes a topic, gathers findings, writes an article, and edits it for publication — all in a single run.

## How it works

Three agents run in sequence:

- **Researcher**: Takes the topic and returns key facts and data points
- **Writer**: Takes the research findings and writes a structured article
- **Editor**: Reviews the draft and outputs the final polished version

Each agent's output becomes the next agent's input.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Environment variables set:
    
    ```bash
    export AGENTSPAN_SERVER_URL=http://localhost:6767/api
    export OPENAI_API_KEY=<YOUR-KEY>
    export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
    ```

## Full code

```python
import os
from agentspan.agents import Agent, AgentRuntime

researcher = Agent(
    name="researcher",
    model=os.environ["AGENTSPAN_LLM_MODEL"],
    instructions=(
        "You are a researcher. Given a topic, provide key facts and data points. "
        "Be thorough but concise. Output raw research findings."
    ),
)

writer = Agent(
    name="writer",
    model=os.environ["AGENTSPAN_LLM_MODEL"],
    instructions=(
        "You are a writer. Take research findings and write a clear, engaging "
        "article. Use headers and bullet points where appropriate."
    ),
)

editor = Agent(
    name="editor",
    model=os.environ["AGENTSPAN_LLM_MODEL"],
    instructions=(
        "You are an editor. Review the article for clarity, grammar, and tone. "
        "Make improvements and output the final polished version."
    ),
)

pipeline = researcher >> writer >> editor

with AgentRuntime() as runtime:
    result = runtime.run(pipeline, "The impact of AI agents on software development in 2025")
    result.print_result()
```

## Run it

Save the file as `research_pipeline.py`, and run it:

```bash
python research_pipeline.py
```

## What this demonstrates
 
```
topic → [researcher] → research brief → [writer] → draft article → [editor] → final article
```
 
**Multi-agent pipeline (`>>`)**: The three agents run sequentially. Each agent sees only the output of the previous one, not the raw prompt. The researcher's output is the writer's input; the writer's output is the editor's input.
 
**Crash recovery**: The pipeline runs on the Agentspan server. If your process dies mid-run, the server resumes from the current agent when you restart. Nothing reruns from scratch.
 
**Run history**: Every execution is stored with inputs, outputs, token usage, and timing. Open `http://localhost:6767` to browse execution history and replay past runs.
 
## Example modifications
 
### Swap models per stage
 
Use a cheaper model for research and a stronger one for writing and editing.
 
```python
researcher = Agent(name="researcher", model="google_gemini/gemini-2.0-flash", ...)
writer     = Agent(name="writer",     model="anthropic/claude-sonnet-4-6", ...)
editor     = Agent(name="editor",     model="openai/gpt-4o", ...)
```
 
### Run multiple topics concurrently
 
Use `start` instead of `run` to kick off multiple pipelines without waiting for each to finish.
 
```python
from agentspan.agents import start
 
topics = [
    "Multi-agent frameworks reshaping software development",
    "LangGraph 1.0 production deployments",
    "CrewAI enterprise customer traction",
]
 
handles = [start(researcher >> writer >> editor, t) for t in topics]
results = [h.stream().get_result() for h in handles]
```
 
### Schedule as a daily job
 
`start` works outside of a `with AgentRuntime()` block — it lazily creates a runtime singleton and shuts it down when the process exits.
 
```python
import schedule, time
from agentspan.agents import start
 
def run_daily():
    for topic in WATCH_LIST:
        start(researcher >> writer >> editor, topic)
 
schedule.every().day.at("07:00").do(run_daily)
while True:
    schedule.run_pending()
    time.sleep(60)
```
