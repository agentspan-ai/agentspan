---
title: LangGraph — code review bot
description: Wrap an existing LangGraph agent with Agentspan for crash recovery, run history, and human-in-the-loop
---

# LangGraph — Code Review Bot

This example shows how to wrap an existing LangGraph agent with Agentspan. The agent reads a GitHub pull request diff, analyses it for bugs, security issues, and style problems, and posts inline review comments — with crash recovery and full run history added by changing one line.

## What Agentspan adds to LangGraph

LangGraph handles your graph — nodes, edges, conditional branching, typed state. Agentspan adds a production execution layer without changing any of that:

- **Crash recovery**: Graph execution runs on the Agentspan server; a process restart picks up the run without re-running completed steps
- **Human-in-the-loop**: Pause at any tool call for human approval, hold state indefinitely server-side, resume cleanly
- **Execution history**: Every run is logged with full inputs, outputs, and timing, browsable at `http://localhost:6767` or via CLI
- **Re-run from history**: Replay any past run with the same input from the UI

Your graph definition, nodes, edges, and typed state schema stay exactly as written.

!!! info "Prerequisites"
    - A running Agentspan server: `agentspan server start`
    - Additional dependencies: `pip install langgraph langchain-anthropic httpx`
    - Environment variables set:
    
    ```bash
    export ANTHROPIC_API_KEY=sk-ant-...
    export GITHUB_TOKEN=ghp_...
    ```
    
    To generate a GitHub token, go to **Settings → Developer settings → Personal access tokens → Tokens (classic)** and check the **`repo`** scope. This gives the bot read access to diffs and write access to post review comments.

---

## Before: plain LangGraph

Standard LangGraph code. It works locally but has no durability — if the process dies mid-review, the run is gone.

```python
import operator
from typing import TypedDict, Annotated
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import os

# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def read_file(path: str) -> str:
    """Read a file from the repository."""
    return open(path).read()

@tool
def get_pr_diff(pr_number: int, repo: str) -> str:
    """Fetch the unified diff for a GitHub pull request."""
    import httpx
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
        headers={"Accept": "application/vnd.github.v3.diff",
                 "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
    )
    return resp.text

@tool
def get_pr_commits(pr_number: int, repo: str) -> str:
    """Get the commits for a GitHub pull request. Call this before post_review_comment to get a valid commit_id."""
    import httpx
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}/commits",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
    )
    return resp.text

@tool
def post_review_comment(pr_number: int, repo: str, body: str, commit_id: str,
                        path: str, line: int) -> dict:
    """Post an inline review comment on a specific line of a PR."""
    import httpx
    resp = httpx.post(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
        json={"body": body, "commit_id": commit_id, "path": path, "line": line},
    )
    return resp.json()

tools = [read_file, get_pr_diff, get_pr_commits, post_review_comment]
tool_node = ToolNode(tools)

# ── Model ─────────────────────────────────────────────────────────────────────

model = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(tools)

SYSTEM = """You are an expert code reviewer. When reviewing a pull request:
1. Fetch the diff with get_pr_diff
2. Fetch the commits with get_pr_commits to get a valid commit_id
3. Read any relevant context files with read_file
4. Identify: bugs, security issues, missing error handling, style violations
5. Post inline comments with post_review_comment for each finding (using the commit_id from step 2)
6. End with a summary of findings and an overall verdict (approve / request changes)"""

# ── Graph ─────────────────────────────────────────────────────────────────────

class State(TypedDict):
    messages: Annotated[list, operator.add]

def agent_node(state: State):
    messages = [SystemMessage(content=SYSTEM)] + state["messages"]
    response = model.invoke(messages)
    return {"messages": [response]}

def should_continue(state: State):
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END

workflow = StateGraph(State)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ── Run ───────────────────────────────────────────────────────────────────────

result = app.invoke({
    "messages": [HumanMessage(content="Review PR #142 in acme-corp/backend")]
})
print(result["messages"][-1].content)
```

---

## After: wrapped with Agentspan

Replace `app.invoke({...})` with `runtime.run(app, {...})`. That's the only change. Agentspan auto-detects LangGraph apps — no extra imports or graph modifications needed.

```python
from agentspan.agents import AgentRuntime

with AgentRuntime() as runtime:
    result = runtime.run(app, {
        "messages": [HumanMessage(content="Review PR #142 in acme-corp/backend")]
    })

print(result.output["messages"][-1].content)
print(f"Run ID: {result.execution_id}")
```

`runtime.run()` registers the graph execution as a managed run on the Agentspan server. The graph logic stays identical — Agentspan wraps the execution lifecycle around it.

---

## What you gain

**Crash recovery**: If your process dies mid-review (network timeout, OOM, deploy restart), Agentspan restarts the graph run when a new worker connects. The run is not lost.

**Run history**: Every PR review is stored with its full input, output, tool calls, and timing. Open `http://localhost:6767` to browse executions and inspect what the model did on each run.

**Re-run**: Replay any past run with the same input directly from the UI. Useful when you update your system prompt or swap models and want to compare outputs.

---

## Run it

Save all the code above (tools, graph, and runtime block) into a single file called `code_review_bot.py`, then run:

```bash
python code_review_bot.py
```

!!! note "Placeholder values"
    `"Review PR #142 in acme-corp/backend"` is a placeholder. Replace it with a real PR number and repository you have access to, otherwise the GitHub API will return a 404.

---

## Example modifications

### Run asynchronously

Use `run_async` in async contexts, such as FastAPI route handlers or async worker loops.

```python
import asyncio
from agentspan.agents import run_async

async def review_pr(pr_number: int, repo: str):
    result = await run_async(app, {
        "messages": [HumanMessage(content=f"Review PR #{pr_number} in {repo}")]
    })
    return result.output["messages"][-1].content

asyncio.run(review_pr(142, "acme-corp/backend"))
```

### Fire-and-forget for long reviews

Use `start` to submit a review and return immediately. Useful when reviews are slow (large diffs, many tool calls) and you don't want to block.

```python
from agentspan.agents import start

# Returns immediately — graph runs in the background on the server
handle = start(app, {
    "messages": [HumanMessage(content="Review PR #142 in acme-corp/backend")]
})

print(f"Started: {handle.execution_id}")

# Collect the result whenever you're ready
result = handle.stream().get_result()
print(result.output["messages"][-1].content)
```

### Review multiple PRs concurrently

`start` works in a loop — each call submits immediately without waiting for the previous one to finish.

```python
from agentspan.agents import start

prs = [(142, "acme-corp/backend"), (87, "acme-corp/frontend"), (23, "acme-corp/infra")]

handles = [
    start(app, {"messages": [HumanMessage(content=f"Review PR #{n} in {repo}")]})
    for n, repo in prs
]

# Block until all reviews are done
results = [h.stream().get_result() for h in handles]
```

---

## Checkpointing and LangSmith

**LangGraph checkpointing** (`MemorySaver`, `PostgresSaver`) saves graph state after each node so a run can resume from where it left off if interrupted. When you wrap with Agentspan, do not use a checkpointer — Agentspan manages the execution lifecycle and the two mechanisms conflict:

```python
# Correct: compile without a checkpointer
app = workflow.compile()

# Do not do this — conflicts with AgentRuntime
# app = workflow.compile(checkpointer=MemorySaver())
```

Agentspan handles crash recovery at the run level. If your worker dies, the graph run restarts from the beginning when a new worker connects. Use Agentspan's recovery instead of LangGraph's node-level checkpointing when the graph is wrapped.

**LangSmith** continues to work as usual. LLM call traces (prompts, completions, token counts) still fire inside the wrapped graph. Agentspan adds run-level tracking on top — execution IDs, full input/output, timing, and status across all your agents — but does not replace per-call LLM traces.

---

## Testing

Use `mock_run` to test the graph without a live server or real API calls. You supply the expected sequence of tool calls and results; `mock_run` drives the graph through them and returns an `AgentResult` you can assert against.

```python
from agentspan.agents.testing import mock_run, MockEvent, expect
from langchain_core.messages import HumanMessage

result = mock_run(
    app,
    {"messages": [HumanMessage(content="Review PR #1 in test/repo")]},
    events=[
        MockEvent.tool_call("get_pr_diff", {"pr_number": 1, "repo": "test/repo"}),
        MockEvent.tool_result("get_pr_diff", "- def foo():\n+ def foo(x: int):"),
        MockEvent.tool_call("post_review_comment", {
            "pr_number": 1,
            "repo": "test/repo",
            "body": "Consider adding a type hint",
            "commit_id": "abc123",
            "path": "main.py",
            "line": 5,
        }),
        MockEvent.tool_result("post_review_comment", {"id": 1, "body": "Consider adding a type hint"}),
        MockEvent.done("Review complete. Posted 1 comment."),
    ]
)

expect(result).completed().used_tool("get_pr_diff").used_tool("post_review_comment")
```
