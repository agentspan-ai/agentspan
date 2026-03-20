# sdk/python/src/agentspan/agents/frameworks/claude_transport.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""AgentspanTransport: Tier 3 replacement for the Claude CLI subprocess.

Makes Anthropic API calls directly and routes tool calls through Conductor SIMPLE tasks.
"""

import asyncio
import json
from typing import AsyncIterator

try:
    from claude_agent_sdk import Transport
except ImportError:

    class Transport:  # type: ignore[no-redef]
        """Stub Transport base class for environments without claude_agent_sdk."""

        async def connect(self) -> None: ...

        async def write(self, data: str) -> None: ...

        def read_messages(self): ...

        async def close(self) -> None: ...

        def is_ready(self) -> bool:
            return True

        async def end_input(self) -> None: ...


try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


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
        Only "user" messages trigger the agentic loop.
        AgentspanTransport is NOT reusable across multiple query() calls.
        """
        msg = json.loads(data)
        if msg["type"] == "user":
            self._conversation.append(msg["message"])
            await self._run_turn()

    def read_messages(self) -> AsyncIterator[dict]:
        """
        Returns an async generator that yields messages until the sentinel.
        read_messages() is a plain synchronous method (not async def) that returns
        an AsyncIterator.
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
            model = self._agent_config.get("model", "claude-opus-4-6")

            # thinking: {"type": "adaptive"} is only valid for Opus/Sonnet 4.6.
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
            # IMPORTANT: thinking blocks MUST be preserved and round-tripped.
            content_dicts = [block.model_dump() for block in response.content]

            # Emit assistant message to SDK
            await self._queue.put(
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": content_dicts},
                    "parent_tool_use_id": None,
                }
            )
            self._conversation.append({"role": "assistant", "content": content_dicts})

            if response.stop_reason != "tool_use":
                break  # done

            # Execute tool calls via Conductor
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    await self._events.push(
                        self._workflow_id,
                        "tool_call",
                        {
                            "toolName": block.name,
                            "args": block.input,
                        },
                    )
                    result = await self._execute_tool(block.name, block.input)
                    await self._events.push(
                        self._workflow_id,
                        "tool_result",
                        {
                            "toolName": block.name,
                            "result": result,
                        },
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            # Emit tool results to SDK and continue loop
            tool_message = {"role": "user", "content": tool_results}
            await self._queue.put(
                {
                    "type": "user",
                    "message": tool_message,
                    "parent_tool_use_id": None,
                }
            )
            self._conversation.append(tool_message)

        # Emit final result, then sentinel to terminate _drain_queue
        final_text = next((b.text for b in response.content if b.type == "text"), "")
        await self._queue.put(
            {
                "type": "result",
                "subtype": "success",
                "result": final_text,
                "session_id": self._workflow_id,
                "is_error": False,
                "num_turns": self._turn_count,
                "duration_ms": 0,
            }
        )
        await self._queue.put(_DRAIN_SENTINEL)

    async def _execute_tool(self, name: str, tool_input: dict) -> str:
        if name == "Agent":
            return await self._run_subagent(tool_input)
        # All other tools → Conductor SIMPLE task
        task_name = f"claude_builtin_{name.lower()}"
        result = await self._conductor.run_task(task_name, {**tool_input, "cwd": self._cwd})
        return result.get("output", "")

    async def _run_subagent(self, tool_input: dict) -> str:
        workflow_name = self._agent_config.get("_worker_name", "claude_agent_workflow")
        sub_workflow_id = await self._conductor.start_workflow(
            workflow_name,
            {"prompt": tool_input.get("prompt", ""), "cwd": self._cwd},
        )
        await self._events.push(
            self._workflow_id, "subagent_start", {"subWorkflowId": sub_workflow_id}
        )
        result = await self._conductor.poll_until_done(sub_workflow_id)
        await self._events.push(
            self._workflow_id,
            "subagent_stop",
            {"subWorkflowId": sub_workflow_id, "result": result},
        )
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
                return
            yield item
