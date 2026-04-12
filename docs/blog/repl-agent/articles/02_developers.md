# Building a Coding Agent from Scratch: What's Really Under the Hood

I've heard people say that agents like Claude Code or Codex are "just wrappers around an LLM."

If you oversimplify things… yeah, that's not entirely wrong, kind of like saying software development is just input → processing → output, IYKWIM.

<!-- TODO: use an agent loop image -->

In practice, there's a lot more engineering behind it.

You need to:

* provide tools the agent can actually use  
* manage context — the right information, at the right time, across interactions  
* and orchestrate all of this in a reliable way

That's where frameworks can help — and there are quite a few out there. I'm part of the team building Agentspan, and through both developing it and using it, I've learned a lot. This post walks through an example I found particularly interesting—one that brings together several of the things I've been working on.

In this post, I'll walk through one of my contributions: a coding agent with a terminal UI (inspired by tools like Claude Code), built with Agentspan and powered by Conductor OSS.

> **Note:** This isn't meant to be a production-ready replacement for those tools. But it *is* a concrete, working example that shows what's really going on under the hood—and how you can build something similar yourself.

---

## What is an Agent, Really?

At a high level, an agent is just a loop:

1. Take input (user message, signal, state)
2. Decide what to do next
3. Optionally call a tool
4. Repeat

You can build this in 50 lines of Python. A `while True`, a call to `openai.chat.completions.create()`, some tool-calling logic, done.

The real challenge isn't the loop—it's what happens when you try to run it in production:

* **Crashes lose everything.** Your agent is mid-task, the process dies, and all state is gone. Conversation history, intermediate results, partial progress—vanished.
* **No visibility.** When something goes wrong, you're grepping through log files trying to reconstruct what the LLM decided and why.
* **Manual retries.** A tool call fails. Now you need to figure out whether to retry, skip, or abort—and you need to write that logic yourself.
* **Concurrent sessions interfere.** Two users run the same agent. Both register workers for `run_shell`. Conductor routes a task from session A to session B's worker. Cross-contamination.

These aren't prompting problems. A smarter model doesn't fix a crashed process or make state durable.

---

## How Agentspan Works

In Agentspan, you don't write the loop. You define the agent—its tools, its model, its instructions—and the framework compiles that definition into a Conductor workflow.

```python
agent = Agent(
    name="coding_agent",
    model="gpt-4.1",
    tools=[
        receive_message, read_file, write_file,
        list_dir, run_shell, find_files,
        search_in_files, reply_to_user,
    ],
    max_turns=100_000,
    stateful=True,
    instructions="""You are a coding assistant with filesystem and shell access.
Working directory: /path/to/project

Repeat indefinitely:
1. Call wait_for_message to receive the next task.
2. Explore, read, modify, and run as needed.
3. Call reply_to_user with a concise summary.
4. Return to step 1.
""",
)
```

At registration time, this compiles to a Conductor workflow definition. Each `@tool` function becomes a Conductor task definition with a worker that polls for work. The LLM call itself is a system task on the server.

The key separation:

* **The LLM decides *what* to do** — which tool to call, with what arguments
* **The system handles *how* it gets done** — task routing, execution, state persistence, retries

This gives you durability (state lives on the server, not in your process), observability (every step is recorded), and control (pause, resume, retry) for free. You don't build that infrastructure—you get it from Conductor.

---

## The REPL Pattern: Interactive Agents

Most agent examples are one-shot: send a prompt, get a result, done. But the interesting use case is a *long-lived interactive agent*—one that loops indefinitely, like a REPL. Think Claude Code: you type a message, the agent works, responds, and waits for your next input.

This might be a bit more tricky than you'd imagine. You might need:

* A way for the agent to *wait* for user input without consuming resources
* A durable message queue so messages aren't lost on network blips
* The ability to send messages while the agent is busy (they should queue up)
* A way to inject context mid-task without interrupting execution

### Under the hood: features that make the REPL possible

#### wait_for_message

The first piece is a special tool:

```python
receive_message = wait_for_message_tool(
    name="wait_for_message",
    description="Wait for the next user message. Payload has a 'text' field.",
)
```

This compiles to a `PULL_WORKFLOW_MESSAGES` task—a server-side task that blocks until a message arrives in the workflow's message queue. No worker needed. The agent calls this tool, and the server holds the execution until something shows up.

On the client side:

```python
runtime.send_message(execution_id, {"text": user_input})
```

This does an HTTP POST to the server. The message lands in a **[Workflow Message Queue (WMQ)](https://github.com/conductor-oss/conductor/pull/982)**—a durable, per-workflow queue stored in the database. The `PULL_WORKFLOW_MESSAGES` task dequeues it, the LLM sees it, and the loop continues.

#### Signals

Messages are great for user input, but what if you want to redirect the agent mid-task? The agent is analyzing 500 files and you realize it's going down the wrong path.

That's where signals come in:

```python
runtime.signal(execution_id, "Focus only on the auth module")
```

A signal sets a workflow variable that the LLM sees on its *next turn*—not the next `wait_for_message`, but the very next LLM invocation. The agent sees `[SIGNALS]Focus only on the auth module[/SIGNALS]` in its context and adjusts behavior. No interruption to the current tool execution, no lost state.

The difference:

| | Messages | Signals |
|---|---|---|
| **Delivery** | Queued, consumed by `wait_for_message` | Injected into workflow variable |
| **When seen** | Next `wait_for_message` call | Next LLM turn |
| **Use case** | User input, new tasks | Course correction, runtime hints |
| **Persistence** | Durable queue | Last-write-wins variable |

---

## The Example: A Coding Agent with Terminal UI

The example ties all of this together. It's a coding agent with:

**Tools** — these are the capabilities exposed to the LLM, so it can decide when and how to use them:
* `read_file`, `write_file` — filesystem access with path validation
* `run_shell` — shell execution with timeout and output truncation
* `find_files`, `search_in_files` — glob patterns and regex search
* `wait_for_message` — blocks for user input (server-side WMQ)
* `reply_to_user` — signals task completion
* (TUI version) `run_background`, `check_process`, `stop_process` — background process management

Here's what one looks like:

```python
@tool
def run_shell(command: str) -> str:
    """Run a shell command in the working directory."""
    proc = subprocess.run(
        command, shell=True, cwd=working_dir,
        capture_output=True, text=True, timeout=shell_timeout,
    )
    return f"[exit {proc.returncode}]\n{(proc.stdout + proc.stderr).strip()}"
```

The `@tool` decorator handles the rest — it reads the function signature and docstring, registers it as a Conductor task, and starts a worker that polls for invocations.

**The REPL loop:**
1. `runtime.start(agent, prompt)` creates and starts the workflow
2. The client reads a stream of Server-Sent Events (SSE) — tool calls, results, status changes — and displays them to the user
3. The user can send messages at any time via `send_message` — they're queued on the server and processed when the agent is ready. Signals can also be sent to inject context mid-task
5. Repeat

If you want to take a look at the full implementation, check out [this PR](https://github.com/agentspan-ai/agentspan/pull/117). There are two examples: a simple one with plain `input()` and another with a simple TUI.

---

## Conclusion

The hard problems in agent development aren't about prompting. They're about distributed systems: durability, observability, isolation, messaging.

Agentspan exists to handle that infrastructure so you can focus on what your agent actually does. You define tools, write instructions, set `stateful=True`, and the framework handles the rest—compilation to workflows, durable execution, session routing, event streaming, and resume.

The coding agent example isn't meant to replace Claude Code. It's meant to show that with the right infrastructure, building an interactive, durable, observable agent is a few hundred lines of Python—not a heroic engineering effort.

And honestly, building it was fun.

