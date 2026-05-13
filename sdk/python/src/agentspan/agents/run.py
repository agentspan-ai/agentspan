# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Convenience execution API — run(), start(), stream(), run_async(), start_async(), stream_async().

These top-level functions provide a quick way to execute agents using a
shared singleton :class:`AgentRuntime`.  They are handy for one-off scripts
but give no control over lifecycle or configuration.

For production use, prefer creating an :class:`AgentRuntime` explicitly::

    from agentspan.agents import Agent, AgentRuntime

    agent = Agent(name="hello", model="openai/gpt-4o")

    with AgentRuntime(server_url="https://play.orkes.io/api") as runtime:
        result = runtime.run(agent, "Hello!")
        print(result.output)

    # Or async:
    async with AgentRuntime() as runtime:
        result = await runtime.run_async(agent, "Hello!")
"""

from __future__ import annotations

import atexit
import logging
import threading
from typing import Any, List, Optional

from agentspan.agents.agent import Agent
from agentspan.agents.result import (
    AgentHandle,
    AgentResult,
    AgentStream,
    AsyncAgentStream,
    DeploymentInfo,
)

logger = logging.getLogger("agentspan.agents.run")

# ── Singleton runtime ────────────────────────────────────────────────────

_default_config: Optional[Any] = None
_default_runtime = None
_runtime_lock = threading.Lock()


def configure(config=None, **kwargs):
    """Pre-configure the default singleton runtime.

    Must be called **before** the first :func:`run`, :func:`start`, or
    :func:`stream` call.  The configuration persists across
    :func:`shutdown` / recreate cycles.

    Args:
        config: An :class:`AgentConfig` instance.  If provided, *kwargs*
            are ignored.
        **kwargs: Individual config fields to override on top of
            :meth:`AgentConfig.from_env` defaults (e.g.
            ``server_url="https://prod:6767/api"``,
            ``auto_start_server=False``).

    Raises:
        RuntimeError: If the singleton runtime already exists.  Call
            :func:`shutdown` first.
        TypeError: If a kwarg does not match an :class:`AgentConfig` field.

    Example::

        import agentspan.agents as ag

        ag.configure(server_url="https://prod:6767/api", auto_start_server=False)
        result = ag.run(agent, "Hello!")
    """
    global _default_config, _default_runtime
    if _default_runtime is not None:
        raise RuntimeError(
            "configure() must be called before the first run/start/stream call. "
            "Call shutdown() first to reset the default runtime."
        )
    if config is not None:
        _default_config = config
    else:
        from agentspan.agents.runtime.config import AgentConfig

        base = AgentConfig.from_env()
        for key, value in kwargs.items():
            if not hasattr(base, key):
                raise TypeError(f"AgentConfig has no field '{key}'")
            setattr(base, key, value)
        _default_config = base


def _get_default_runtime():
    """Return (or create) the module-level default AgentRuntime singleton."""
    global _default_runtime
    if _default_runtime is None:
        with _runtime_lock:
            if _default_runtime is None:
                from agentspan.agents.runtime.runtime import AgentRuntime

                _default_runtime = AgentRuntime(config=_default_config)
                logger.info("Created default AgentRuntime singleton")
    return _default_runtime


def _shutdown_default_runtime():
    """Gracefully shut down the singleton runtime at process exit."""
    global _default_runtime
    if _default_runtime is not None:
        logger.info("Shutting down default AgentRuntime singleton")
        _default_runtime.shutdown()
        _default_runtime = None


atexit.register(_shutdown_default_runtime)


def shutdown() -> None:
    """Shut down the default singleton runtime, stopping all worker processes.

    Call this for explicit cleanup in long-running servers. In simple scripts
    with daemon workers (the default), this is not necessary — workers are
    killed automatically when the process exits.

    Example::

        from agentspan.agents import run, shutdown

        result = run(agent, "Hello!")
        shutdown()  # explicit cleanup
    """
    _shutdown_default_runtime()


# ── Deploy & Serve ──────────────────────────────────────────────────────


def deploy(
    *agents: Any,
    packages: Optional[List[str]] = None,
    runtime: Optional[Any] = None,
) -> List[DeploymentInfo]:
    """Compile and register agents on the server without executing them.

    This is a CI/CD operation.  See :meth:`AgentRuntime.deploy`.

    Args:
        *agents: Agent objects to deploy.
        packages: Python packages to scan for Agent instances.
        runtime: Optional custom :class:`AgentRuntime`.

    Returns:
        List of :class:`DeploymentInfo`, one per deployed agent.
    """
    rt = runtime or _get_default_runtime()
    return rt.deploy(*agents, packages=packages)


async def deploy_async(
    *agents: Any,
    packages: Optional[List[str]] = None,
    runtime: Optional[Any] = None,
) -> List[DeploymentInfo]:
    """Async version of :func:`deploy`."""
    rt = runtime or _get_default_runtime()
    return await rt.deploy_async(*agents, packages=packages)


def serve(
    *agents: Any,
    packages: Optional[List[str]] = None,
    blocking: bool = True,
    runtime: Optional[Any] = None,
) -> None:
    """Register workers and keep them polling until interrupted.

    This is a runtime operation.  See :meth:`AgentRuntime.serve`.

    Args:
        *agents: Agents whose workers should be served.
        packages: Python packages to scan for Agent instances.
        blocking: If ``True`` (default), blocks until Ctrl+C / SIGTERM.
        runtime: Optional custom :class:`AgentRuntime`.
    """
    rt = runtime or _get_default_runtime()
    rt.serve(*agents, packages=packages, blocking=blocking)


# ── Sync convenience functions ───────────────────────────────────────────


def plan(
    agent: Agent,
    *,
    runtime: Optional[Any] = None,
) -> Any:
    """Compile an agent to a workflow definition without executing it.

    Returns the raw server response with ``workflowDef`` and
    ``requiredWorkers`` keys.  Does NOT register workflows, start
    workers, or execute anything.

    Args:
        agent: The :class:`Agent` to compile.
        runtime: Optional custom :class:`AgentRuntime`.

    Returns:
        A dict with ``workflowDef`` (the Conductor workflow definition)
        and ``requiredWorkers``.

    Example::

        from agentspan.agents import Agent, tool, plan

        @tool
        def greet(name: str) -> str:
            return f"Hello {name}"

        agent = Agent(name="greeter", model="openai/gpt-4o", tools=[greet])
        result = plan(agent)
        print(result["workflowDef"]["name"])   # "greeter"
        print(result["workflowDef"]["tasks"])  # list of task definitions
    """
    rt = runtime or _get_default_runtime()
    return rt.plan(agent)


def run(
    agent: Agent,
    prompt: "Any",
    *,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    on_event: Optional[Any] = None,
    credentials: Optional[List[str]] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AgentResult:
    """Execute an agent synchronously and return the result.

    Blocks until the agent completes (or fails). This is the simplest way
    to run an agent.

    Args:
        agent: The :class:`Agent` to execute.
        prompt: The user's input message.
        media: Optional list of media URLs (images, video, audio) to
            include with the prompt.
        session_id: Optional session ID for multi-turn conversation continuity.
        idempotency_key: Optional key to prevent duplicate executions.
        on_event: Optional callback invoked for each streaming event.
            When provided, the agent runs via SSE and calls
            ``on_event(event)`` as events arrive.
        runtime: Optional custom :class:`AgentRuntime`. If not provided, a
            shared singleton runtime is used.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AgentResult` with the agent's output, conversation history,
        tool calls, and workflow metadata.

    Example::

        from agentspan.agents import Agent, run

        agent = Agent(name="helper", model="openai/gpt-4o")
        result = run(agent, "What is 2 + 2?")
        print(result.output)
    """
    rt = runtime or _get_default_runtime()
    return rt.run(
        agent,
        prompt,
        media=media,
        session_id=session_id,
        idempotency_key=idempotency_key,
        on_event=on_event,
        credentials=credentials,
        **kwargs,
    )


def start(
    agent: Agent,
    prompt: "Any",
    *,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AgentHandle:
    """Start an agent (fire-and-forget) and return a handle.

    Returns immediately with a handle that can be used to check status,
    interact with human-in-the-loop pauses, and control the execution
    from any process.

    Args:
        agent: The :class:`Agent` to execute.
        prompt: The user's input message.
        media: Optional list of media URLs (images, video, audio).
        session_id: Optional session ID for multi-turn conversation continuity.
        idempotency_key: Optional key to prevent duplicate executions.
        runtime: Optional custom :class:`AgentRuntime`.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AgentHandle` for monitoring and interacting with the agent.

    Example::

        from agentspan.agents import Agent, start

        agent = Agent(name="analyzer", model="openai/gpt-4o")
        handle = start(agent, "Analyze all Q4 reports")
        print(handle.execution_id)

        # Later, from any process:
        status = handle.get_status()
        if status.is_complete:
            print(status.output)
    """
    rt = runtime or _get_default_runtime()
    return rt.start(
        agent, prompt, media=media, session_id=session_id, idempotency_key=idempotency_key, **kwargs
    )


def stream(
    agent: Optional[Agent] = None,
    prompt: "Optional[Any]" = None,
    *,
    handle: Optional[AgentHandle] = None,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AgentStream:
    """Execute an agent and stream events as they occur.

    Can be called in two ways:

    1. ``stream(agent, prompt)`` — starts a new workflow.
    2. ``stream(handle=handle)`` — streams from an existing workflow.

    Returns an :class:`AgentStream` — iterable (yields events), with HITL
    convenience methods and access to the final :class:`AgentResult`.

    Args:
        agent: The :class:`Agent` to execute (required unless *handle* is given).
        prompt: The user's input message (required unless *handle* is given).
        handle: An existing :class:`AgentHandle` to stream from.
        media: Optional list of media URLs (images, video, audio).
        session_id: Optional session ID for multi-turn conversation continuity.
        runtime: Optional custom :class:`AgentRuntime`.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AgentStream`.

    Example::

        from agentspan.agents import Agent, stream

        agent = Agent(name="writer", model="openai/gpt-4o")
        for event in stream(agent, "Write a haiku"):
            if event.type == "done":
                print(event.output)
    """
    rt = runtime or _get_default_runtime()
    return rt.stream(agent, prompt, handle=handle, media=media, session_id=session_id, **kwargs)


# ── Async convenience functions ──────────────────────────────────────────


async def run_async(
    agent: Agent,
    prompt: "Any",
    *,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    on_event: Optional[Any] = None,
    credentials: Optional[List[str]] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AgentResult:
    """Execute an agent asynchronously (``await``-able).

    Async counterpart of :func:`run`. Uses ``httpx.AsyncClient`` for
    non-blocking HTTP communication with the server.

    Args:
        agent: The :class:`Agent` to execute.
        prompt: The user's input message.
        media: Optional list of media URLs (images, video, audio).
        session_id: Optional session ID for multi-turn conversation continuity.
        idempotency_key: Optional key to prevent duplicate executions.
        on_event: Optional callback invoked for each streaming event.
        runtime: Optional custom :class:`AgentRuntime`.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AgentResult` with the agent's output.

    Example::

        import asyncio
        from agentspan.agents import Agent, run_async

        agent = Agent(name="helper", model="openai/gpt-4o")
        result = asyncio.run(run_async(agent, "Hello!"))
    """
    rt = runtime or _get_default_runtime()
    return await rt.run_async(
        agent,
        prompt,
        media=media,
        session_id=session_id,
        idempotency_key=idempotency_key,
        on_event=on_event,
        credentials=credentials,
        **kwargs,
    )


async def start_async(
    agent: Agent,
    prompt: "Any",
    *,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AgentHandle:
    """Start an agent asynchronously and return a handle.

    Async counterpart of :func:`start`.

    Args:
        agent: The :class:`Agent` to execute.
        prompt: The user's input message.
        media: Optional list of media URLs (images, video, audio).
        session_id: Optional session ID for multi-turn conversation continuity.
        idempotency_key: Optional key to prevent duplicate executions.
        runtime: Optional custom :class:`AgentRuntime`.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AgentHandle`.

    Example::

        import asyncio
        from agentspan.agents import Agent, start_async

        agent = Agent(name="analyzer", model="openai/gpt-4o")
        handle = asyncio.run(start_async(agent, "Analyze reports"))
    """
    rt = runtime or _get_default_runtime()
    return await rt.start_async(
        agent, prompt, media=media, session_id=session_id, idempotency_key=idempotency_key, **kwargs
    )


def resume(
    execution_id: str,
    agent: Agent,
    *,
    runtime: Optional[Any] = None,
) -> AgentHandle:
    """Re-attach to an existing agent execution and re-register workers.

    Convenience wrapper around :meth:`AgentRuntime.resume`.  Fetches the
    workflow from the server, extracts the worker domain from its
    ``taskToDomain`` mapping, and re-registers tool workers.

    Args:
        execution_id: The Conductor execution ID from a previous
            :func:`start` call.
        agent: The same :class:`Agent` definition originally executed.
        runtime: Optional custom :class:`AgentRuntime`.

    Returns:
        An :class:`AgentHandle` bound to the runtime with workers
        polling under the correct domain.

    Example::

        from agentspan.agents import Agent, start, resume

        agent = Agent(name="worker", model="openai/gpt-4o", tools=[...])
        handle = start(agent, "Long job")
        eid = handle.execution_id

        # Later (even after a restart):
        handle = resume(eid, agent)
        result = handle.join(timeout=120)
    """
    rt = runtime or _get_default_runtime()
    return rt.resume(execution_id, agent)


async def resume_async(
    execution_id: str,
    agent: Agent,
    *,
    runtime: Optional[Any] = None,
) -> AgentHandle:
    """Async version of :func:`resume`.

    Args:
        execution_id: The Conductor execution ID.
        agent: The same :class:`Agent` definition originally executed.
        runtime: Optional custom :class:`AgentRuntime`.

    Returns:
        An :class:`AgentHandle`.
    """
    rt = runtime or _get_default_runtime()
    return await rt.resume_async(execution_id, agent)


async def stream_async(
    agent: Optional[Agent] = None,
    prompt: "Optional[Any]" = None,
    *,
    handle: Optional[AgentHandle] = None,
    media: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    runtime: Optional[Any] = None,
    **kwargs: Any,
) -> AsyncAgentStream:
    """Execute an agent and stream events asynchronously.

    Async counterpart of :func:`stream`.

    Can be called in two ways:

    1. ``await stream_async(agent, prompt)`` — starts a new workflow.
    2. ``await stream_async(handle=handle)`` — streams from existing workflow.

    Returns an :class:`AsyncAgentStream` — async-iterable that yields
    :class:`AgentEvent` objects.

    Args:
        agent: The :class:`Agent` to execute (required unless *handle* is given).
        prompt: The user's input message (required unless *handle* is given).
        handle: An existing :class:`AgentHandle` to stream from.
        media: Optional list of media URLs (images, video, audio).
        session_id: Optional session ID for multi-turn conversation continuity.
        runtime: Optional custom :class:`AgentRuntime`.
        **kwargs: Additional workflow input parameters.

    Returns:
        An :class:`AsyncAgentStream`.

    Example::

        import asyncio
        from agentspan.agents import Agent, stream_async

        async def main():
            agent = Agent(name="writer", model="openai/gpt-4o")
            async for event in await stream_async(agent, "Write a haiku"):
                if event.type == "done":
                    print(event.output)

        asyncio.run(main())
    """
    rt = runtime or _get_default_runtime()
    return await rt.stream_async(
        agent, prompt, handle=handle, media=media, session_id=session_id, **kwargs
    )
