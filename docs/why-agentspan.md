---
title: Why Agentspan
description: Why agents fail in production, and how Agentspan's server-side execution model solves it.
---

# Why Agentspan

**Agentspan is a durable runtime for AI agents, built for Conductor. Your code runs in your process. Execution state lives on the server — so crashes, restarts, and deployments don't lose work.**

This page covers why conventional agent frameworks fail in production, how Agentspan's server-side execution model addresses those failures, and when Agentspan is the right choice.

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

**No scheduling without external infrastructure.** Running an agent on a cron means maintaining a separate scheduler, handling missed fires, and managing overlap. Any of those can fail silently — and there's no execution history tied to your agent when it does.

**Background jobs block or disappear.** Firing an agent asynchronously in-process — via threading or asyncio — means the job dies when your process does. There's no durable handle, no execution record, and no way to push new events into it from another process.

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

**Scheduled agents.** Attach one or more crons to any agent at deploy time. The server fires the agent on cadence, tracks every execution, and lets you pause, resume, or trigger ad-hoc — without touching application code. See [Scheduling](scheduling.md).

**Background execution.** `runtime.start()` returns an `AgentHandle` immediately — the agent runs on the server. From any process, use the handle to check status, stream events, or push new inputs into the running agent with `runtime.send_message(execution_id, event)`. Works from webhook handlers, Kafka consumers, queue workers, or any event source.

**Plan-Execute: LLM plans, Conductor executes.** Define a planner agent that emits a JSON DAG of operations. The server compiles it into a Conductor sub-workflow — no LLM involved in orchestration, retries, parallelism, or validation. The planner runs once; the rest is deterministic and replay-safe. This is the defining superpower of Agentspan + Conductor. See [Plan-Execute](concepts/plan-execute.md).

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
