# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agents SDK compatibility — drop-in Runner replacement.

Change one import line::

    # Before
    from agents import Runner

    # After
    from agentspan import Runner

Your agents now run on Agentspan instead of directly against OpenAI.
Agentspan adds durability, observability, human-in-the-loop, and horizontal
scaling — no other code changes needed.

Compatible with openai-agents-python ``Agent``, ``@function_tool``, and
``Runner.run_sync`` / ``Runner.run`` / ``Runner.run_streamed``.

Example::

    from agentspan import Runner
    from agents import Agent, function_tool   # keep the rest unchanged

    @function_tool
    def get_weather(city: str) -> str:
        \"\"\"Return the current weather for a city.\"\"\"
        return f"72°F and sunny in {city}"

    agent = Agent(
        name="helper",
        model="gpt-4o",
        tools=[get_weather],
        instructions="You are a helpful assistant.",
    )

    result = Runner.run_sync(agent, "What's the weather in NYC?")
    print(result.final_output)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("agentspan.agents.openai_compat")


# ── RunResult ─────────────────────────────────────────────────────────────


class RunResult:
    """Return value of Runner.run_sync / Runner.run.

    Mirrors the ``openai-agents`` ``RunResult`` interface so code that
    accesses ``result.final_output`` works without any changes.

    Attributes:
        final_output: The agent's final text output.
    """

    def __init__(self, agent_result: Any) -> None:
        self._agent_result = agent_result

    @property
    def final_output(self) -> Any:
        """The agent's final output — same attribute as openai-agents RunResult."""
        output = self._agent_result.output
        if isinstance(output, dict):
            return output.get("result", output)
        return output

    @property
    def execution_id(self) -> str:
        """The Agentspan execution ID for debugging."""
        return self._agent_result.execution_id

    def __repr__(self) -> str:
        return f"RunResult(final_output={self.final_output!r})"


# ── Helpers ────────────────────────────────────────────────────────────────


def _model_to_agentspan(model: str) -> str:
    """Add a provider prefix when the model name lacks one.

    ``"gpt-4o"``         → ``"openai/gpt-4o"``
    ``"claude-opus-4-6"``→ ``"anthropic/claude-opus-4-6"``
    ``"openai/gpt-4o"``  → ``"openai/gpt-4o"``  (already qualified)
    """
    if "/" in model:
        return model
    if model.startswith(("gpt", "o1", "o3", "o4")):
        return f"openai/{model}"
    if model.startswith("claude"):
        return f"anthropic/{model}"
    if model.startswith("gemini"):
        return f"google/{model}"
    return f"openai/{model}"


def _run_async_safely(coro: Any) -> Any:
    """Run a coroutine in the current or a new event loop.

    Handles three contexts:
    - No event loop running → ``asyncio.run()``
    - Event loop running but we're in a worker thread → new ``asyncio.run()``
    - Event loop running and we ARE on it → thread-pool escape
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


def _convert_function_tool(ft: Any) -> Any:
    """Convert an openai-agents ``FunctionTool`` to an Agentspan ``ToolDef``.

    Args:
        ft: Object with ``.name``, ``.description``, ``.params_json_schema``,
            and ``.on_invoke_tool(ctx, input_json_str)`` attributes.

    Returns:
        An Agentspan :class:`~agentspan.agents.tool.ToolDef`.
    """
    from agentspan.agents.tool import ToolDef

    tool_name: str = ft.name
    tool_desc: str = getattr(ft, "description", "") or ""
    schema: dict = getattr(ft, "params_json_schema", {})
    on_invoke = ft.on_invoke_tool

    def _sync_wrapper(**kwargs: Any) -> Any:
        input_json = json.dumps(kwargs)
        result = on_invoke(None, input_json)
        if asyncio.iscoroutine(result):
            return _run_async_safely(result)
        return result

    _sync_wrapper.__name__ = tool_name
    _sync_wrapper.__doc__ = tool_desc

    return ToolDef(
        name=tool_name,
        description=tool_desc,
        input_schema=schema,
        func=_sync_wrapper,
        tool_type="worker",
    )


def _to_agentspan_agent(agent: Any) -> Any:
    """Convert an openai-agents ``Agent`` to an Agentspan ``Agent``.

    If *agent* is already an Agentspan ``Agent`` it is returned unchanged.
    Duck-typed: any object with ``name``, ``instructions``, ``model``,
    and ``tools`` attributes is accepted.
    """
    from agentspan.agents.agent import Agent

    if isinstance(agent, Agent):
        return agent

    name: str = getattr(agent, "name", "openai_agent")

    instructions: Any = getattr(agent, "instructions", "")
    if callable(instructions):
        try:
            result = instructions()
            instructions = asyncio.run(result) if asyncio.iscoroutine(result) else result
        except Exception:
            instructions = ""
    if not isinstance(instructions, str):
        instructions = str(instructions) if instructions else ""

    model: str = _model_to_agentspan(getattr(agent, "model", "openai/gpt-4o"))

    raw_tools: list = getattr(agent, "tools", []) or []
    agentspan_tools = []
    for t in raw_tools:
        if hasattr(t, "on_invoke_tool"):
            agentspan_tools.append(_convert_function_tool(t))
        elif hasattr(t, "_tool_def"):
            agentspan_tools.append(t)
        else:
            logger.warning(
                "Skipping unrecognised tool type '%s' — "
                "wrap it with Agentspan's @tool decorator to include it.",
                type(t).__name__,
            )

    return Agent(
        name=name,
        instructions=instructions,
        model=model,
        tools=agentspan_tools,
    )


# ── Runner ─────────────────────────────────────────────────────────────────


class Runner:
    """Drop-in replacement for ``openai-agents`` Runner.

    Identical call signatures — swap one import and the rest of your code
    stays unchanged::

        # change this:
        from agents import Runner

        # to this:
        from agentspan import Runner

    Methods
    -------
    ``Runner.run_sync(agent, input)``
        Synchronous execution.  Returns a :class:`RunResult`.
    ``await Runner.run(agent, input)``
        Async execution.  Returns a :class:`RunResult`.
    ``Runner.run_streamed(agent, input)``
        Streaming execution.  Returns an Agentspan :class:`AsyncAgentStream`.
    """

    @classmethod
    def run_sync(
        cls,
        starting_agent: Any,
        input: str,
        *,
        context: Optional[Any] = None,
        max_turns: int = 10,
        **kwargs: Any,
    ) -> RunResult:
        """Run an agent synchronously.

        Drop-in for ``Runner.run_sync(agent, input)``.

        Args:
            starting_agent: An openai-agents ``Agent`` or Agentspan ``Agent``.
            input: The user's input message.
            context: Ignored — present only for openai-agents API compatibility.
            max_turns: Maximum agent loop iterations.
            **kwargs: Extra keyword arguments (ignored for forward compatibility).

        Returns:
            A :class:`RunResult` with a ``final_output`` attribute.
        """
        from agentspan.agents.run import run as agentspan_run

        agent = _to_agentspan_agent(starting_agent)
        if max_turns != 10:
            agent.max_turns = max_turns

        result = agentspan_run(agent, input)
        return RunResult(result)

    @classmethod
    async def run(
        cls,
        starting_agent: Any,
        input: str,
        *,
        context: Optional[Any] = None,
        max_turns: int = 10,
        **kwargs: Any,
    ) -> RunResult:
        """Run an agent asynchronously.

        Drop-in for ``await Runner.run(agent, input)``.

        Args:
            starting_agent: An openai-agents ``Agent`` or Agentspan ``Agent``.
            input: The user's input message.
            context: Ignored — present only for openai-agents API compatibility.
            max_turns: Maximum agent loop iterations.
            **kwargs: Extra keyword arguments (ignored for forward compatibility).

        Returns:
            A :class:`RunResult` with a ``final_output`` attribute.
        """
        from agentspan.agents.run import run_async

        agent = _to_agentspan_agent(starting_agent)
        if max_turns != 10:
            agent.max_turns = max_turns

        result = await run_async(agent, input)
        return RunResult(result)

    @classmethod
    async def run_streamed(
        cls,
        starting_agent: Any,
        input: str,
        *,
        context: Optional[Any] = None,
        max_turns: int = 10,
        **kwargs: Any,
    ) -> Any:
        """Run an agent with live event streaming.

        Drop-in for ``Runner.run_streamed(agent, input)``.

        Returns an Agentspan :class:`~agentspan.agents.result.AsyncAgentStream`
        which supports ``async for event in stream`` iteration.

        Note: Agentspan event types (``"tool_call"``, ``"done"``, etc.) differ
        from openai-agents ``StreamEvent`` types.  For full streaming event
        compatibility, iterate and map events as needed.

        Args:
            starting_agent: An openai-agents ``Agent`` or Agentspan ``Agent``.
            input: The user's input message.
            context: Ignored — present only for openai-agents API compatibility.
            max_turns: Maximum agent loop iterations.
            **kwargs: Extra keyword arguments (ignored for forward compatibility).

        Returns:
            An :class:`~agentspan.agents.result.AsyncAgentStream`.
        """
        from agentspan.agents.run import stream_async

        agent = _to_agentspan_agent(starting_agent)
        if max_turns != 10:
            agent.max_turns = max_turns

        return await stream_async(agent, input)
