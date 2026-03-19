# Claude Agent SDK Integration for Agentspan

**Date:** 2026-03-19
**Status:** Draft (v2 — reviewer issues resolved)

## Summary

Add support for running Claude Agent SDK agents on Agentspan with three tiers of integration: (1) durable passthrough execution with full event observability, (2) Claude's internal subagents compiled to real Conductor SUB_WORKFLOWs, and (3) all tool execution routed through Conductor SIMPLE tasks via a custom Transport. Each tier is a superset of the previous. Tiers 2 and 3 are opt-in via flags.

---

## Why This Is Different From Every Other Framework

LangGraph, LangChain, OpenAI Agents, and Google ADK all make HTTP calls to an LLM and execute tools via Python function calls. Agentspan can intercept at either the LLM call boundary or the tool call boundary.

The Claude Agent SDK is categorically different:

- It **spawns the Claude Code CLI as a local subprocess** and communicates via JSON over stdio
- The CLI process runs its own autonomous agentic loop — LLM calls, tool execution, and subagent spawning all happen **inside the subprocess**
- The SDK (Python) only answers permission checks and hook callbacks via a control protocol; it never executes tools itself
- Tools (`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebSearch`, `WebFetch`) run on **localhost** — the same machine as the worker
- Sessions persist as JSONL conversation history files on the local filesystem at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`

The SDK's hook system (`PreToolUse`, `PostToolUse`, etc.) can observe and block tool calls via the control protocol, but **cannot inject custom tool results for built-in tools** — the CLI always executes and returns results itself. Replacing tool results requires either a custom `Transport` implementation (Tier 3) or an MCP shim (excluded here due to tool-naming concerns).

---

## Architecture Overview

```
Tier 1 (always on)         Tier 2 (conductor_subagents=True)    Tier 3 (agentspan_routing=True)
─────────────────────      ──────────────────────────────────    ──────────────────────────────
Conductor SUB_WORKFLOW      same                                  same
  └─ SIMPLE worker            └─ SIMPLE worker                     └─ SIMPLE worker
       └─ query()                  └─ query()                           └─ query()
            ├─ hooks                    ├─ hooks                              └─ AgentspanTransport
            │   push events            │   push events                            ├─ Anthropic API (LLM)
            │   outbound               │   outbound                               ├─ tools → Conductor SIMPLE
            │                          └─ Agent tool:                             └─ Agent tool → SUB_WORKFLOW
            └─ session                     PreToolUse denies
                persist                    native execution,
                on server                  starts Conductor
                                           SUB_WORKFLOW,
                                           polls for result
```

---

## Tier 1: Durable Passthrough + Event Observability

### Execution Model

The entire `query()` call runs as a single Conductor SIMPLE task inside a Conductor SUB_WORKFLOW. This matches the LangGraph/LangChain passthrough pattern. The worker uses hooks to stream events to the Agentspan SSE infrastructure via outbound HTTP POSTs.

```
User prompt
    │
    ▼
Agentspan Server ──compiles──▶ Passthrough WorkflowDef
                                (one SIMPLE task, _fw_claude_ prefix)
    │
    ▼
Conductor dispatches SIMPLE task to Python worker
    │
    ▼
Worker:
  1. GET /api/agent-sessions/{workflowId}  → restore session JSONL
  2. query(prompt, options, resume=session_id)
        ├─ PreToolUse hook  → POST /api/agent/events/{workflowId} { type: "tool_call" }
        ├─ PostToolUse hook → POST /api/agent/events/{workflowId} { type: "tool_result" }
        │                     POST /api/agent-sessions/{workflowId} (checkpoint JSONL)
        ├─ SubagentStart    → POST /api/agent/events/{workflowId} { type: "subagent_start" }
        └─ SubagentStop     → POST /api/agent/events/{workflowId} { type: "subagent_stop" }
  3. ResultMessage → return TaskResult(COMPLETED)
```

All event POSTs are non-blocking (dispatched to a background thread pool). Session checkpoints (PostToolUse) are awaited to ensure consistency.

### Session Durability

Sessions are stored on the Agentspan server, keyed by `workflowInstanceId`. This decouples session state from the worker machine, allowing Conductor to retry on any available worker.

**Session lifecycle:**

| Moment | Worker action |
|---|---|
| Task start | `GET /api/agent-sessions/{workflowId}` — restore JSONL to local path, pass `session_id` to `query()` |
| After every tool call (PostToolUse hook) | `POST /api/agent-sessions/{workflowId}` — upload current JSONL content |
| Task complete | No-op (already checkpointed after last tool) |
| Task retry (worker crash) | New worker: `GET` retrieves last checkpoint, resumes seamlessly |

**Session file location:**

The Claude CLI stores sessions at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. Rather than replicating the CLI's exact path-encoding algorithm (which is subject to change), the worker locates the file using the session ID as a glob:

```python
import glob, os

def find_session_file(session_id: str) -> str | None:
    """Locate the CLI session JSONL by session ID — avoids encoding algorithm dependency."""
    pattern = os.path.expanduser(f"~/.claude/projects/**/{session_id}.jsonl")
    matches = glob.glob(pattern, recursive=True)
    return matches[0] if matches else None

def write_session_file(session_id: str, cwd: str, jsonl_content: str) -> str:
    """
    Write restored JSONL to the expected path.
    The path is derived by glob-searching for the session_id after the first run,
    or by inspecting the CLI source for the encoding algorithm.

    Empirical verification required: run the SDK once, observe the path created
    under ~/.claude/projects/, and confirm the encoding scheme before shipping.
    The known format is: ~/.claude/projects/<url-percent-encoded-absolute-cwd>/<session-id>.jsonl
    """
    # Verify encoding against actual CLI behavior before deploying
    import urllib.parse
    encoded_cwd = urllib.parse.quote(os.path.abspath(cwd), safe='')
    path = os.path.expanduser(f"~/.claude/projects/{encoded_cwd}/{session_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(jsonl_content)
    return path
```

**Important:** The exact encoding scheme (`urllib.parse.quote` vs. a custom scheme) must be verified empirically against the CLI before the session restore feature ships. If encoding mismatches, the session file will be written to a path the CLI does not read, causing silent session loss. The glob-based `find_session_file()` is used for reading (after the CLI has already created the path) and avoids this dependency.

**No session found** (first run or session expired): `query()` starts fresh, `SystemMessage(subtype="init")` emits the new `session_id`, which is included in the first checkpoint.

### Hook Infrastructure

All hooks are registered as async Python callbacks. They share closure over `workflow_id`, `session_id_ref` (populated after `SystemMessage(init)`), `cwd`, and the HTTP client.

**Event field names must match what `AgentService.pushFrameworkEvent()` reads on the Java side:** `toolName`, `args`, `result` (not `tool`, `input`, `output`).

```python
# sdk/python/src/agentspan/agents/frameworks/claude.py (simplified)
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher, SystemMessage, ResultMessage

def make_claude_worker(agent_config, session_client, event_client, conductor_client=None):

    def worker(task):
        workflow_id = task.workflow_instance_id
        prompt = task.input_data["prompt"]
        cwd = task.input_data.get("cwd", ".")
        session_id_ref = {"value": None}

        async def pre_tool_hook(input_data, tool_use_id, context):
            await event_client.push(workflow_id, "tool_call", {
                "toolName": input_data["tool_name"],
                "args": input_data["tool_input"],
            })
            return {}

        async def post_tool_hook(input_data, tool_use_id, context):
            await event_client.push(workflow_id, "tool_result", {
                "toolName": input_data["tool_name"],
                "result": input_data.get("tool_response"),
            })
            await session_client.checkpoint(workflow_id, session_id_ref["value"], cwd)
            return {}

        async def subagent_start_hook(input_data, tool_use_id, context):
            # Fires for native SDK subagents (Tier 1 passthrough, or Tier 2 when
            # conductor_subagents=False). The SDK provides agent_id and agent_type.
            # No subWorkflowId is available here — this is an in-process subagent.
            await event_client.push(workflow_id, "subagent_start", {
                "agentId": input_data.get("agent_id"),
                "agentType": input_data.get("agent_type"),
                "subWorkflowId": None,  # native subagent; no Conductor workflow
            })
            return {}

        async def subagent_stop_hook(input_data, tool_use_id, context):
            await event_client.push(workflow_id, "subagent_stop", {
                "agentId": input_data.get("agent_id"),
                "subWorkflowId": None,
            })
            return {}

        hooks = {
            "PreToolUse":   [HookMatcher(matcher=".*", hooks=[pre_tool_hook])],
            "PostToolUse":  [HookMatcher(matcher=".*", hooks=[post_tool_hook])],
            "SubagentStart":[HookMatcher(matcher=".*", hooks=[subagent_start_hook])],
            "SubagentStop": [HookMatcher(matcher=".*", hooks=[subagent_stop_hook])],
        }

        if agent_config.get("conductor_subagents") and conductor_client:
            # Tier 2: intercept Agent tool and route to Conductor.
            # When conductor_subagents=True, the SubagentStart/SubagentStop hooks above
            # will NOT fire for Agent-tool invocations (they are denied before spawning).
            # subagent_start/subagent_stop events for Conductor-routed subagents are
            # pushed by make_subagent_hook below with the actual subWorkflowId populated.
            subagent_hook = make_subagent_hook(conductor_client, event_client, workflow_id, cwd, agent_config)
            hooks["PreToolUse"].append(HookMatcher(matcher="Agent", hooks=[subagent_hook]))

        async def run():
            session_id = session_client.restore(workflow_id, cwd)
            async for msg in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=cwd,
                    allowed_tools=agent_config.get("allowed_tools", []),
                    max_turns=agent_config.get("max_turns", 100),
                    resume=session_id,
                    system_prompt=agent_config.get("system_prompt"),  # None → SDK uses default
                    hooks=hooks,
                ),
            ):
                if isinstance(msg, SystemMessage) and msg.subtype == "init":
                    session_id_ref["value"] = msg.session_id
                if isinstance(msg, ResultMessage):
                    return msg.result
            return None

        # asyncio.run() always creates a new event loop.
        # Conductor workers run in dedicated threads with no existing event loop — this is safe.
        result = asyncio.run(run())
        from agentspan.agents import TaskResult, COMPLETED
        return TaskResult(status=COMPLETED, output_data={"result": result})

    return worker
```

---

## Tier 2: Subagents as Conductor SUB_WORKFLOWs (`conductor_subagents=True`)

### Mechanism

The Claude Agent SDK has a built-in `Agent` tool that spawns internal subagents. By default these run entirely inside the CLI subprocess, invisible to Conductor. With `conductor_subagents=True`, an additional `PreToolUse` hook intercepts the `Agent` tool call **before** the CLI spawns its own subprocess.

The hook:
1. Denies the native `Agent` tool execution (`permissionDecision: "deny"`)
2. Starts a real Conductor SUB_WORKFLOW for the subagent (outbound POST to Conductor)
3. Polls for completion (outbound GETs — no inbound connections required)
4. Returns the result in the denial reason

```python
def make_subagent_hook(conductor_client, event_client, workflow_id, cwd, agent_config):
    """
    Note: event_client must be passed explicitly — it is not captured from outer scope.
    This function is used both when building Tier 1/2 hooks in make_claude_worker()
    and standalone for testing.
    """
    async def subagent_hook(input_data, tool_use_id, context):
        if input_data["tool_name"] != "Agent":
            return {}

        tool_input = input_data["tool_input"]
        sub_workflow_id = await conductor_client.start_workflow(
            workflow_name="claude_agent_workflow",
            input={
                "prompt": tool_input.get("prompt", ""),
                "cwd": cwd,
                **agent_config.get("subagent_overrides", {}),
            }
        )

        await event_client.push(workflow_id, "subagent_start", {
            "subWorkflowId": sub_workflow_id,
            "prompt": tool_input.get("prompt", ""),
        })

        result = await conductor_client.poll_until_done(sub_workflow_id)

        await event_client.push(workflow_id, "subagent_stop", {
            "subWorkflowId": sub_workflow_id,
            "result": result,
        })

        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Subagent completed via Agentspan workflow {sub_workflow_id}.\n\n"
                    f"Result:\n{result}"
                ),
            }
        }

    return subagent_hook
```

### Trade-off: Denial vs. Tool Result

The SDK control protocol does not allow injecting a custom tool result for built-in tools — only allow or deny. Deny is used here, with the actual subagent result embedded in `permissionDecisionReason`. The conversation history records a "denied Agent tool" rather than a successful tool invocation.

Claude handles this gracefully: it reads the denial reason, extracts the result, and continues its task. The functional correctness is maintained. The semantic impurity (denial vs. success) is accepted as the cost of avoiding MCP tool-naming changes.

### Subagent Config Inheritance

The subagent Conductor workflow runs `claude_agent_workflow`, which is the same compiled workflow used for top-level Claude agents. `subagent_overrides` in the parent agent config can specify different `allowed_tools`, `max_turns`, etc. for subagents. If absent, defaults are used.

---

## Tier 3: All Tools via Conductor (`agentspan_routing=True`)

### Why a Custom Transport

To route regular tools (`Bash`, `Read`, `Write`, etc.) to Conductor SIMPLE tasks with clean, proper tool results (not denials), the SDK's hook system is insufficient — it cannot inject tool results for built-in tools. The only path that produces semantically clean conversation history is a custom `Transport` that replaces the CLI subprocess entirely.

The `Transport` ABC is explicitly exposed by the SDK as an extension point for "remote Claude Code connections" (per its docstring). It is in `__all__` and has been stable since v0.0.22. It carries an explicit `WARNING` that it may change in future releases — this integration is isolated behind the `agentspan_routing` flag so that any breaking SDK update affects only users who have opted in.

### AgentspanTransport Architecture

`AgentspanTransport` replaces the CLI subprocess. It speaks the same `stream-json` protocol to the SDK above it, but drives the LLM loop itself using the Anthropic Messages API, and routes tool execution to Conductor below it.

```
SDK (query.py control loop)
        │  stream-json protocol
        ▼
AgentspanTransport
        ├─ write(data)      ← receives prompts and control responses from SDK
        ├─ read_messages()  ← yields synthesized stream-json messages to SDK
        │
        ├─ Anthropic Messages API  (LLM turns)
        │
        ├─ Tool calls detected in assistant message content
        │     ├─ Bash, Read, Write, Edit, Glob, Grep
        │     │     └─ Conductor SIMPLE task (claude_builtin_workers.py)
        │     │           outbound POST to Conductor → poll for result
        │     └─ Agent tool
        │           └─ Conductor SUB_WORKFLOW (same as Tier 2)
        │
        └─ Synthesizes tool_result messages → yields back to SDK
```

Because `AgentspanTransport` handles all tool execution directly, **SDK hooks (`PreToolUse`, `PostToolUse`, etc.) do not fire** when `agentspan_routing=True` — the CLI hook-callback control messages are never sent. Instead, `AgentspanTransport` pushes events to the Agentspan event system directly (at the same points where hooks would have fired).

### stream-json Message Protocol

The Transport synthesizes these message types for the SDK:

```json
// Assistant turn (after Anthropic API call)
{"type": "assistant", "message": {"role": "assistant", "content": [...]}, "parent_tool_use_id": null}

// Tool result (after Conductor task completes)
{"type": "user", "message": {"role": "user", "content": [
  {"type": "tool_result", "tool_use_id": "tu_abc123", "content": "result text", "is_error": false}
]}, "parent_tool_use_id": null}

// Final result — session_id is the workflow_id (Tier 3 has no CLI-assigned session ID)
{"type": "result", "subtype": "success", "result": "...", "session_id": "<workflow_id>",
 "duration_ms": 12345, "num_turns": 5, "is_error": false}
```

**Note on `session_id` in result message:** In Tier 3, the CLI subprocess is replaced entirely by `AgentspanTransport`. There is no CLI-assigned session ID. The workflow ID is used as a stable, unique identifier in its place. Session persistence is handled by the Transport directly (not by the CLI), so this does not affect correctness.

### Conversation State

`AgentspanTransport` maintains the conversation history in memory across turns. Each LLM call appends to the history; tool results are appended as user messages. Session persistence works the same as Tier 1/2 (JSONL saved to Agentspan server) but the JSONL is written by the Transport directly rather than via SDK session management.

### AgentspanTransport Implementation Sketch

```python
# sdk/python/src/agentspan/agents/frameworks/claude_transport.py

import asyncio, json, anthropic
from claude_agent_sdk import Transport
from typing import AsyncIterator

_DRAIN_SENTINEL = object()  # signals _drain_queue to stop iteration

# Tool schemas for the Anthropic Messages API (Tier 3 — Transport makes LLM calls directly)
_TOOL_SCHEMAS = {
    "Bash": {
        "name": "Bash",
        "description": "Execute shell commands",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        },
    },
    "Read": {
        "name": "Read",
        "description": "Read a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["file_path"],
        },
    },
    "Write": {
        "name": "Write",
        "description": "Write content to a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
    },
    "Edit": {
        "name": "Edit",
        "description": "Edit a file by replacing text",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    "Glob": {
        "name": "Glob",
        "description": "Find files by glob pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": "."},
            },
            "required": ["pattern"],
        },
    },
    "Grep": {
        "name": "Grep",
        "description": "Search file contents by regex pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": "."},
                "glob_pattern": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    "WebSearch": {
        "name": "WebSearch",
        "description": "Search the web",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    "WebFetch": {
        "name": "WebFetch",
        "description": "Fetch a web page",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    "Agent": {
        "name": "Agent",
        "description": "Spawn a subagent to handle a subtask",
        "input_schema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
}


class AgentspanTransport(Transport):
    def __init__(self, agent_config, conductor_client, event_client, workflow_id, cwd):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._conversation: list = []
        self._agent_config = agent_config
        self._conductor = conductor_client
        self._events = event_client
        self._workflow_id = workflow_id
        self._cwd = cwd
        self._client = anthropic.AsyncAnthropic()
        self._turn_count = 0

    async def connect(self) -> None:
        pass  # nothing to connect to

    async def write(self, data: str) -> None:
        """
        Called by the SDK to send a message to the transport.

        Lifecycle: the SDK calls write() once with the initial user prompt, then
        reads messages until the result sentinel. For a single query() invocation,
        write() is called exactly once. AgentspanTransport is NOT reusable across
        multiple query() calls — create a new instance per query.

        Other message types (e.g., SDK system initialization) are intentionally
        ignored; only "user" messages trigger the agentic loop.
        """
        msg = json.loads(data)
        if msg["type"] == "user":
            # New user prompt received — start the agentic loop
            self._conversation.append(msg["message"])
            await self._run_turn()

    def read_messages(self) -> AsyncIterator[dict]:
        """
        Returns an async generator that yields messages until the sentinel.

        read_messages() is a plain synchronous method (not async def) that returns
        an AsyncIterator. This is consistent with the Transport ABC. Calling
        self._drain_queue() returns the async generator object synchronously;
        the SDK iterates it with `async for`. Verified: Transport ABC declares
        read_messages() as `def`, not `async def`.
        """
        return self._drain_queue()

    def _get_tool_schemas(self) -> list:
        """Return Anthropic tool schemas for allowed_tools."""
        allowed = set(self._agent_config.get("allowed_tools", []))
        return [schema for name, schema in _TOOL_SCHEMAS.items() if name in allowed]

    # Models that support adaptive thinking (Anthropic API parameter)
    _ADAPTIVE_THINKING_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

    async def _run_turn(self) -> None:
        while True:
            # LLM call via Anthropic Messages API
            model = self._agent_config.get("model", "claude-opus-4-6")

            # thinking: {"type": "adaptive"} is only valid for Opus/Sonnet 4.6.
            # For other models, omit the parameter entirely.
            thinking_param = (
                {"thinking": {"type": "adaptive"}}
                if model in self._ADAPTIVE_THINKING_MODELS
                else {}
            )

            create_kwargs = {
                "model": model,
                "max_tokens": self._agent_config.get("max_tokens", 8192),
                "messages": self._conversation,
                "tools": self._get_tool_schemas(),
                **thinking_param,
            }
            if self._agent_config.get("system_prompt"):
                create_kwargs["system"] = self._agent_config["system_prompt"]

            response = await self._client.messages.create(**create_kwargs)
            self._turn_count += 1

            # Serialize content blocks for the stream-json protocol.
            # Anthropic SDK objects must be converted to dicts before JSON serialization.
            content_dicts = [block.model_dump() for block in response.content]

            # Emit assistant message to SDK
            await self._queue.put({
                "type": "assistant",
                "message": {"role": "assistant", "content": content_dicts},
                "parent_tool_use_id": None,
            })
            self._conversation.append({"role": "assistant", "content": content_dicts})

            if response.stop_reason != "tool_use":
                break  # done

            # Execute tool calls via Conductor
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    await self._events.push(self._workflow_id, "tool_call", {
                        "toolName": block.name,
                        "args": block.input,
                    })
                    result = await self._execute_tool(block.name, block.input)
                    await self._events.push(self._workflow_id, "tool_result", {
                        "toolName": block.name,
                        "result": result,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Emit tool results to SDK and continue loop
            tool_message = {"role": "user", "content": tool_results}
            await self._queue.put({
                "type": "user",
                "message": tool_message,
                "parent_tool_use_id": None,
            })
            self._conversation.append(tool_message)

        # Emit final result, then sentinel to terminate _drain_queue
        final_text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        await self._queue.put({
            "type": "result",
            "subtype": "success",
            "result": final_text,
            # In Tier 3, no CLI-assigned session ID exists; workflow_id is used as
            # a stable unique identifier. Session state is managed by the Transport.
            "session_id": self._workflow_id,
            "is_error": False,
            "num_turns": self._turn_count,
            "duration_ms": 0,
        })
        # Sentinel tells _drain_queue to stop — without it, read_messages() blocks forever
        await self._queue.put(_DRAIN_SENTINEL)

    async def _execute_tool(self, name: str, tool_input: dict) -> str:
        if name == "Agent":
            return await self._run_subagent(tool_input)
        # All other tools → Conductor SIMPLE task
        task_name = f"claude_builtin_{name.lower()}"
        result = await self._conductor.run_task(task_name, {
            **tool_input, "cwd": self._cwd
        })
        return result.get("output", "")

    async def _run_subagent(self, tool_input: dict) -> str:
        sub_workflow_id = await self._conductor.start_workflow(
            "claude_agent_workflow",
            {"prompt": tool_input.get("prompt", ""), "cwd": self._cwd}
        )
        await self._events.push(self._workflow_id, "subagent_start",
                                {"subWorkflowId": sub_workflow_id})
        result = await self._conductor.poll_until_done(sub_workflow_id)
        await self._events.push(self._workflow_id, "subagent_stop",
                                {"subWorkflowId": sub_workflow_id, "result": result})
        return result

    async def close(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        pass

    async def _drain_queue(self):
        """Yield items from the queue until the sentinel is received."""
        while True:
            item = await self._queue.get()
            if item is _DRAIN_SENTINEL:
                return  # terminates the async generator; query() sees StopAsyncIteration
            yield item
```

---

## Built-in Tool Workers (`claude_builtin_workers.py`)

Used only when `agentspan_routing=True`. All workers live in a single file and are started together. Each receives `cwd` from the task input (passed by `AgentspanTransport`).

**Security note:** File path operations use `.resolve()` and check that the result stays within `cwd` to prevent path traversal. `claude_builtin_bash` uses `shell=True` and must only be deployed in controlled environments (see Limitations).

```python
# sdk/python/src/agentspan/agents/frameworks/claude_builtin_workers.py

import subprocess, pathlib, glob as glob_module, re, json, os
import anthropic
from agentspan.agents import tool, AgentRuntime


def _safe_path(cwd: str, file_path: str) -> pathlib.Path:
    """Resolve file_path within cwd, raising ValueError on traversal attempts."""
    base = pathlib.Path(cwd).resolve()
    resolved = (base / file_path).resolve()
    if not str(resolved).startswith(str(base) + os.sep) and resolved != base:
        raise ValueError(f"Path '{file_path}' escapes working directory")
    return resolved


@tool
def claude_builtin_bash(command: str, timeout: int = 30, cwd: str = ".") -> dict:
    """
    SECURITY: Runs with shell=True. Deploy only in controlled environments
    with pre-vetted agent prompts. Consider Docker sandboxing for production.
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout, cwd=cwd
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return {"output": output, "exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"output": f"Command timed out after {timeout}s", "exit_code": 124}


@tool
def claude_builtin_read(file_path: str, offset: int = 0, limit: int = None, cwd: str = ".") -> dict:
    try:
        path = _safe_path(cwd, file_path)
        lines = path.read_text().splitlines(keepends=True)
        if offset:
            lines = lines[offset:]
        if limit:
            lines = lines[:limit]
        return {"output": "".join(lines), "total_lines": len(lines)}
    except ValueError as e:
        return {"output": str(e), "exit_code": 1}
    except FileNotFoundError:
        return {"output": f"File not found: {file_path}", "exit_code": 1}


@tool
def claude_builtin_write(file_path: str, content: str, cwd: str = ".") -> dict:
    try:
        path = _safe_path(cwd, file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {"output": f"Wrote {len(content)} bytes to {file_path}"}
    except ValueError as e:
        return {"output": str(e), "exit_code": 1}


@tool
def claude_builtin_edit(file_path: str, old_string: str, new_string: str,
                         replace_all: bool = False, cwd: str = ".") -> dict:
    try:
        path = _safe_path(cwd, file_path)
        content = path.read_text()
        count = content.count(old_string)
        if count == 0:
            return {"output": f"Error: string not found in {file_path}", "exit_code": 1}
        if count > 1 and not replace_all:
            return {"output": f"Error: string appears {count} times; use replace_all=True", "exit_code": 1}
        path.write_text(content.replace(old_string, new_string, None if replace_all else 1))
        return {"output": f"Replaced {count if replace_all else 1} occurrence(s)"}
    except ValueError as e:
        return {"output": str(e), "exit_code": 1}


@tool
def claude_builtin_glob(pattern: str, path: str = ".", cwd: str = ".") -> dict:
    try:
        base = _safe_path(cwd, path)
        matches = [str(p) for p in base.glob(pattern)]
        return {"output": "\n".join(sorted(matches)), "count": len(matches)}
    except ValueError as e:
        return {"output": str(e), "exit_code": 1}


@tool
def claude_builtin_grep(pattern: str, path: str = ".", glob_pattern: str = None,
                         cwd: str = ".") -> dict:
    try:
        base = _safe_path(cwd, path)
        file_glob = glob_pattern or "**/*"
        results = []
        for f in base.glob(file_glob):
            if not f.is_file():
                continue
            try:
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if re.search(pattern, line):
                        results.append(f"{f}:{i}: {line}")
            except (UnicodeDecodeError, PermissionError):
                pass
        return {"output": "\n".join(results), "count": len(results)}
    except ValueError as e:
        return {"output": str(e), "exit_code": 1}


@tool
def claude_builtin_websearch(query: str) -> dict:
    """Search the web using Claude's server-side web search tool."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": query}],
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return {"output": text}


@tool
def claude_builtin_webfetch(url: str, prompt: str = None) -> dict:
    """Fetch and summarize a web page using Claude's server-side web fetch tool."""
    client = anthropic.Anthropic()
    content = f"Fetch {url}"
    if prompt:
        content += f" and {prompt}"
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
        tools=[{"type": "web_fetch_20260209", "name": "web_fetch"}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return {"output": text}


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        runtime.start()
```

**Tool naming convention:** The transport uses `claude_builtin_{tool_name_lower}` to construct the Conductor task name. Note: `WebSearch` → `claude_builtin_websearch`, `WebFetch` → `claude_builtin_webfetch` (no underscore in the function name, since the SDK uses single-word tool names).

---

## User-Facing API

```python
from agentspan.agents import AgentRuntime
from agentspan.frameworks.claude import ClaudeCodeAgent

# Tier 1: passthrough with observability
agent = ClaudeCodeAgent(
    prompt="Analyze this codebase for security vulnerabilities",
    cwd="/path/to/project",
    allowed_tools=["Read", "Glob", "Grep", "Bash"],
    max_turns=50,
)

# Tier 2: subagents become real Conductor SUB_WORKFLOWs
agent = ClaudeCodeAgent(
    prompt="Research and implement a fix for the auth bug",
    cwd="/path/to/project",
    allowed_tools=["Read", "Write", "Edit", "Bash", "Agent"],
    conductor_subagents=True,
)

# Tier 3: all tools route through Conductor
agent = ClaudeCodeAgent(
    prompt="Set up the CI pipeline and run tests",
    cwd="/path/to/project",
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob"],
    agentspan_routing=True,   # implies conductor_subagents=True
    model="claude-opus-4-6",
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "")
```

`ClaudeCodeAgent` can also be used as a sub-agent tool in a multi-agent setup with other Agentspan agents (OpenAI, ADK, LangGraph):

```python
from agentspan.agents import Agent, tool
from agentspan.frameworks.claude import ClaudeCodeAgent

code_analyst = ClaudeCodeAgent(
    name="code_analyst",
    allowed_tools=["Read", "Glob", "Grep"],
    cwd="/path/to/project",
)

orchestrator = Agent(
    name="orchestrator",
    model="openai/gpt-4o",
    tools=[code_analyst],  # Claude agent wrapped as an Agentspan tool → SUB_WORKFLOW
)
```

---

## `ClaudeCodeAgent` Configuration Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | required | The task prompt |
| `cwd` | `str` | `"."` | Working directory passed to all tool workers |
| `allowed_tools` | `list[str]` | `[]` | Claude SDK built-in tools to permit |
| `max_turns` | `int` | `100` | Maximum agent turns |
| `model` | `str` | `"claude-opus-4-6"` | Model (used only by Tier 3 Transport) |
| `max_tokens` | `int` | `8192` | Max output tokens per LLM call (Tier 3 only) |
| `system_prompt` | `str` | `None` | Custom system prompt override |
| `conductor_subagents` | `bool` | `False` | Tier 2: route `Agent` tool to Conductor SUB_WORKFLOWs |
| `agentspan_routing` | `bool` | `False` | Tier 3: route all tools to Conductor; implies `conductor_subagents=True` |
| `subagent_overrides` | `dict` | `{}` | Config overrides for spawned subagent workflows |

---

## Server-Side Changes (Java)

### New: Session Storage Endpoints

Added to `AgentController` (mapped to `/api/agent`):

```
GET    /api/agent-sessions/{workflowId}
       → returns { sessionId, jsonlContent } or 404

POST   /api/agent-sessions/{workflowId}
       Body: { sessionId: str, jsonlContent: str }
       → 200 OK; upserts session record

DELETE /api/agent-sessions/{workflowId}
       → 200 OK; used on workflow cleanup
```

Session records are stored in a new `AgentSession` entity in the existing database (one row per workflowId). `jsonlContent` is stored as a TEXT column (CLOB for large sessions). Cleanup is triggered when the parent workflow is deleted or archived.

### Modified: `AgentCompiler.java` — Add `cwd` to WORKFLOW_INPUTS

`WORKFLOW_INPUTS` currently contains `["prompt", "session_id", "media"]`. `cwd` must be added so that `compileFrameworkPassthrough()` maps it to the Conductor workflow input and the Python worker can read it from `task.input_data.get("cwd")`.

**File to change:** `server/src/main/java/dev/agentspan/runtime/compiler/AgentCompiler.java`
**Change:** Add `"cwd"` to the `WORKFLOW_INPUTS` list and ensure `compileFrameworkPassthrough()` includes it in the workflow input mapping. Without this, the worker always receives `cwd = "."` regardless of what the user specified.

### New: `ClaudeAgentNormalizer.java`

Normalizes `ClaudeCodeAgent` rawConfig → passthrough `AgentConfig`. Identical pattern to `LangGraphNormalizer`.

```json
// rawConfig sent by Python SDK
{
  "name": "my_claude_agent",
  "_worker_name": "my_claude_agent",
  "conductor_subagents": false,
  "agentspan_routing": false
}
```

Produces:
```java
AgentConfig {
  name: "my_claude_agent",
  metadata: {
    "_framework_passthrough": true,
    "_claude_conductor_subagents": false,
    "_claude_agentspan_routing": false
  },
  tools: [ ToolConfig { name: "my_claude_agent", toolType: "worker" } ]
}
```

### Modified: `AgentCompiler.java` — `isFrameworkPassthrough()` Check

No additional changes needed. Existing `isFrameworkPassthrough()` check handles Claude agents because `_framework_passthrough: true` is set in metadata. The passthrough guard already runs before any model-dependent branching.

### Modified: `AgentEventListener.java`

The existing `_fw_` prefix check on `taskReferenceName` already suppresses spurious tool events for passthrough workers. Claude agents use the same `_fw_claude_` prefix convention.

### Modified: `AgentService.java` — Add `subagent_start` and `subagent_stop` Event Types

`AgentService.pushFrameworkEvent()` currently handles: `thinking`, `tool_call`, `tool_result`, `context_condensed`. The `subagent_start` and `subagent_stop` events pushed by Claude workers and the Transport will be **silently dropped** unless this method is extended.

**Required changes to `AgentService.java`:**
1. Add `case "subagent_start":` handler that extracts `subWorkflowId` (Tier 2 / Tier 3) or `agentId` (Tier 1 native subagent) — use whichever is non-null for the display identifier. Call `AgentSSEEvent.subagentStart(workflowId, identifier, payload.get("prompt"))`.
2. Add `case "subagent_stop":` handler — same identifier extraction. Call `AgentSSEEvent.subagentStop(workflowId, identifier, payload.get("result"))`.

**Required changes to `AgentSSEEvent.java` (or equivalent factory class):**
Add factory methods `subagentStart(String workflowId, String subagentIdentifier, String prompt)` and `subagentStop(String workflowId, String subagentIdentifier, String result)` returning the appropriate SSE event objects.

Wire `AgentSessionService` dependency for session CRUD and cleanup on workflow deletion events.

---

## SSE Event Mapping

Events pushed by the worker (Tier 1/2) or Transport (Tier 3) to `POST /api/agent/events/{workflowId}`.

**Event payload field names match what `AgentService.pushFrameworkEvent()` reads:** `toolName`, `args`, `result`, `subWorkflowId` (not `tool`, `input`, `output`, `sub_workflow_id`).

**There are two sources of subagent events with different payloads:**

| Source | SSE event | Payload |
|---|---|---|
| `PreToolUse` fires for any non-Agent tool | `tool_call` | `{toolName, args}` |
| `PostToolUse` fires for any tool | `tool_result` | `{toolName, result}` |
| SDK `SubagentStart` hook (Tier 1 / native subagent) | `subagent_start` | `{agentId, agentType, subWorkflowId: null}` |
| SDK `SubagentStop` hook (Tier 1 / native subagent) | `subagent_stop` | `{agentId, subWorkflowId: null}` |
| Tier 2 `make_subagent_hook` (Conductor-routed subagent) | `subagent_start` | `{subWorkflowId, prompt, agentId: null}` |
| Tier 2 `make_subagent_hook` (Conductor-routed subagent) | `subagent_stop` | `{subWorkflowId, result, agentId: null}` |
| Conductor workflow → COMPLETED | `done` (fired by existing `AgentEventListener`, same as all agents) | — |

`AgentService.pushFrameworkEvent()` must handle both payload shapes for `subagent_start`/`subagent_stop`: use `subWorkflowId` when non-null, fall back to `agentId` for display.

Tier 3 pushes the same events directly from `AgentspanTransport` (since SDK hooks don't fire when Transport replaces the CLI). Tier 3 subagent events always use the Conductor-routed shape (with `subWorkflowId`).

---

## Error Handling

| Failure | Behavior |
|---|---|
| Worker process crash | Conductor retries task; new worker restores from last checkpoint |
| Session checkpoint fails (network) | Log warning, continue execution; worst case: retry loses last tool's progress |
| Anthropic API error (Tier 3) | Transport raises; worker returns `TaskResult(FAILED)`; Conductor retries with exponential backoff |
| Conductor task fails (tool execution, Tier 3) | Transport injects error tool_result; Claude decides whether to retry or abandon |
| Subagent SUB_WORKFLOW fails | `poll_until_done` raises; denial reason contains error; Claude handles gracefully |
| Session JSONL parse error on restore | Skip restore (start fresh); log warning |
| `max_turns` exceeded | `ResultMessage.stop_reason = "max_turns"`; return partial result as COMPLETED |
| SDK subprocess crash (Tier 1/2) | Worker returns `FAILED`; Conductor retries; session restores from checkpoint |
| Session file path mismatch (encoding) | `find_session_file()` returns None; treated as no-session (fresh start); logs warning |

---

## File Changes

### Python SDK (`sdk/python/src/agentspan/agents/`)

| File | Change |
|---|---|
| `frameworks/claude.py` | **New** — `ClaudeCodeAgent` class, worker factory, Tier 1/2 hooks, session client, event client |
| `frameworks/claude_transport.py` | **New** — `AgentspanTransport` (Tier 3), full Transport ABC implementation |
| `frameworks/claude_builtin_workers.py` | **New** — 8 built-in tool workers (`claude_builtin_*`), single-file, `AgentRuntime.start()` entrypoint |
| `frameworks/serializer.py` | **Modified** — add `ClaudeCodeAgent` to `detect_framework()` and `serialize_agent()` dispatch |
| `frameworks/__init__.py` | **Modified** — export `ClaudeCodeAgent` |
| `runtime/runtime.py` | **Modified** — two changes: (1) in `_start_framework()` and `_start_framework_async()`, extend the existing `if framework in ("langgraph", "langchain"):` guard to also include `"claude"` so it calls `_register_passthrough_worker()` instead of `_register_framework_workers()`; (2) in `_build_passthrough_func()`, add `elif framework == "claude":` branch that calls `make_claude_worker(agent_config, session_client, event_client, conductor_client)` |

### Java Server (`server/src/main/java/dev/agentspan/runtime/`)

| File | Change |
|---|---|
| `normalizer/ClaudeAgentNormalizer.java` | **New** — rawConfig → passthrough `AgentConfig` |
| `controller/AgentController.java` | **Modified** — add `GET/POST/DELETE /api/agent-sessions/{workflowId}` |
| `service/AgentSessionService.java` | **New** — CRUD for session JSONL storage |
| `model/AgentSession.java` | **New** — JPA entity for session storage |
| `service/AgentService.java` | **Modified** — add `subagent_start`/`subagent_stop` event handlers; wire `AgentSessionService` for cleanup |
| `compiler/AgentCompiler.java` | **Modified** — add `"cwd"` to `WORKFLOW_INPUTS`; include in passthrough workflow input mapping |
| `event/AgentSSEEvent.java` | **Modified** — add `subagentStart()` and `subagentStop()` factory methods |

---

## Limitations & Known Trade-offs

1. **Tier 2 denial semantics**: Subagent results are carried in a tool denial reason, not a proper tool result. Conversation history is semantically impure. Functionally correct but may affect Claude's reasoning quality in edge cases.

2. **Transport stability**: `AgentspanTransport` depends on the SDK's `Transport` ABC, which carries an explicit stability warning. Isolated behind `agentspan_routing=True` flag. Must be validated on each SDK version bump.

3. **Session files are local first**: Worker writes session JSONL locally before uploading to the server. If the machine loses power before the first PostToolUse checkpoint, session is lost for that turn. Acceptable given the tool-call checkpoint granularity.

4. **Tier 3 tool parity**: `claude_builtin_workers.py` implements the 8 built-in Claude SDK tools. If Anthropic adds new built-in tools to the SDK, they will silently route to Conductor as unknown tools until added to the workers file.

5. **No TypeScript SDK support**: This design covers the Python SDK only. TypeScript support is a follow-up.

6. **`web_search` and `web_fetch` cost**: Both workers make separate Anthropic API calls. In Tier 3, this means a Claude agent using web search incurs two model calls per web search (one from the Transport's LLM turn, one from the worker). Acceptable for now.

7. **`claude_builtin_bash` security**: The bash worker runs commands with `shell=True`, which allows shell injection if an untrusted agent controls command construction. Deploy only in controlled environments with pre-vetted prompts. Consider Docker or similar sandboxing for production workloads.

8. **Session file path encoding**: The exact URL-encoding scheme used by the Claude CLI must be verified empirically before the session restore feature ships. A mismatch causes silent session loss (treated as fresh start). The glob-based `find_session_file()` mitigates read-side risk but the write-side (restore to worker) requires correct path derivation.

9. **Adaptive thinking model requirement**: `thinking: {"type": "adaptive"}` requires `claude-opus-4-6` or `claude-sonnet-4-6`. `AgentspanTransport._run_turn()` guards on `_ADAPTIVE_THINKING_MODELS` and omits the parameter for other models. If a user configures an older model, thinking is silently disabled.

---

## Out of Scope

- TypeScript SDK support
- `AskUserQuestion` tool routing (stays native; maps to Agentspan's existing HumanTask if needed in a follow-up)
- Computer use tool support
- Multi-modal inputs (image/file content in prompts)
- Claude Agent SDK TypeScript/Node.js variant
- LangGraph-within-Claude-agent nesting
