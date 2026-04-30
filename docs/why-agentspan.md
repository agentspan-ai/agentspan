---
title: Why Agentspan
description: Why agents fail in production, and how Agentspan's server-side execution model solves it.
---

# Why Agentspan

**Agentspan is a durable runtime for AI agents. Your code runs in your process. Execution state lives on the server — so crashes, restarts, and deployments don't lose work.**

---

## How most agent frameworks work

Most agent frameworks — LangGraph, the OpenAI Agents SDK, Google ADK, and others — run the agent loop inside your process. Your code calls the LLM, receives a tool call, executes the tool, and loops. All of that happens in memory, in your process.

```
Your process
└── agent loop
    ├── call LLM
    ├── execute tool
    ├── call LLM again
    └── ...until done
```

This works fine on your laptop. In production, it breaks in predictable ways.

---

## What can go wrong

**Process crash mid-run.** A long-running agent — one that searches the web, reads files, calls APIs across dozens of steps — can take minutes. If your process dies (OOM kill, deploy, network drop), the entire run is gone. There is no way to resume from where it stopped.

**Human-in-the-loop doesn't survive restarts.** Pausing an agent to wait for a human approval means holding state in memory. If anything interrupts that wait — a timeout, a restart, a deploy — the approval request is lost and the agent can't resume.

**No history, no replay.** In-process execution leaves no record. You can't see what an agent did on a past run, replay a run with a different model, or query execution history across agents.

**Scaling means duplicating state.** Running agents across multiple machines means solving distributed state management yourself — or accepting that each agent instance is isolated with no shared execution context.

---

## How Agentspan works differently

Agentspan separates where your code runs from where execution state lives.

```
Your process                    Agentspan server
└── worker                      └── agent execution
    ├── registers tools             ├── tracks current step
    └── executes tool calls ←──────── delegates tool work
                                    ├── retries on failure
                                    ├── holds HITL state
                                    └── stores full history
```

Your agent definition compiles into a durable workflow on the Agentspan server. The server orchestrates execution — calling your worker to run tools, tracking state at every step, and resuming from the last completed step if anything goes wrong.

Your process can crash, restart, or be replaced. The agent keeps running.

---

## What this enables

**Crash recovery.** If your worker process dies mid-run, the server resumes execution when a new worker connects. No work is re-run from scratch — it picks up at the current step.

**Durable human-in-the-loop.** Mark any tool with `approval_required=True`. The agent pauses server-side and waits indefinitely — no timeouts, no in-memory state at risk. Approve or deny via CLI, API, or the UI.

**Full execution history.** Every run is stored with inputs, outputs, token usage, and per-step timing. Query via CLI, browse in the UI at `http://localhost:6767`, or replay any past run.

**Works with frameworks you already use.** Pass a LangGraph `StateGraph`, an OpenAI Agents SDK `Agent`, or a Google ADK pipeline directly to `runtime.run()`. Your definitions stay unchanged.

---

## Frequently asked questions

**What makes Agentspan different from LangGraph?**
LangGraph is a graph framework for defining agent routing logic — nodes, edges, conditional branching. Agentspan is an execution runtime. You can pass a compiled LangGraph app directly to `runtime.run()` and it gains crash recovery, HITL, and execution history without changing a single node. They work together.

**What makes Agentspan different from the OpenAI Agents SDK?**
The OpenAI Agents SDK defines agents, handoffs, and tools. Its execution model is in-process. Agentspan wraps that execution so it runs server-side — your agent definitions, handoffs, and tools stay exactly as written.

**When should I use Agentspan?**
Whenever agents need to run reliably in production: long-running tasks, human approval steps, jobs that must survive process restarts, or situations where you need a queryable history of what every agent did.

**Does Agentspan replace my existing framework?**
No. If you use LangGraph, the OpenAI Agents SDK, or Google ADK, pass your existing agent directly to `runtime.run()`. If you write agents natively, use the `Agent` class — one Python object with tools, instructions, and strategy.

**What model providers does Agentspan support?**
Any provider with an OpenAI-compatible API. Set the model with one string: `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4-6"`, `"google_gemini/gemini-2.0-flash"`. See [LLM Providers](/docs/providers) for the full list.
