# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""HarnessRuntime — entry point for the coding-agent harness.

The harness session **is** an agentspan ``Agent`` execution. The harness's
job is to assemble a Pythonic toolset (``read_file``, ``write_file``,
``shell``, ``patch_file``, GitHub tools, etc.), wrap each tool with
permission / sandbox / hook checks, and hand it to an :class:`Agent` that
runs as a Conductor workflow.

That gives us, for free:

* The conversation loop (``LLM_CHAT_COMPLETE`` ↔ tool calls) executes
  server-side in Conductor.
* Per-user credentials come from the credential vault
  (``AgentspanAIModelProvider``).
* Server-side history compaction
  (``AgentChatCompleteTaskMapper.compactToolHistory``).
* Resume after kill via the worker-liveness re-attach machinery
  (``runtime.resume(execution_id, agent)``).
* Telemetry, retries, SSE streaming.
* Multi-provider support (any model litellm could reach, Conductor
  can reach via its native provider clients — Anthropic, OpenAI, Gemini,
  Bedrock, Mistral, Cohere, Grok, Perplexity, HuggingFace, Azure).

Ergonomic API:

    runtime = HarnessRuntime(HarnessConfig(
        model="anthropic/claude-sonnet-4-6",
        tools=default_full_tools(),
        cwd="/path/to/repo",
        sandbox=ChecksOnlySandbox(allowed_read_roots=["/path/to/repo"]),
        permission_engine=PermissionEngine(rules=[...]),
        system="You are a coding agent.",
    ))
    async for event in runtime.submit("Fix the bug in src/foo.py"):
        ...
    runtime.close()
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TYPE_CHECKING

from .permission.engine import PermissionEngine
from .permission.rules import PermissionMode
from .sandbox.interface import Sandbox
from .shared_store import SharedStore
from .tasks import TaskManager
from .tools.contract import Tool
from .worktree import WorktreeManager

if TYPE_CHECKING:
    from agentspan.agents.runtime.runtime import AgentRuntime  # noqa: F401

logger = logging.getLogger("agentspan.harness.runtime")


# ── Configuration ─────────────────────────────────────────────────────────


@dataclass
class HarnessConfig:
    """Construction-time configuration for a :class:`HarnessRuntime`.

    The provider is no longer a config option — every call goes through
    Conductor's ``LLM_CHAT_COMPLETE`` task. Set the model with the
    ``provider/model`` syntax (e.g. ``"anthropic/claude-sonnet-4-6"``).
    """

    model: str
    tools: List[Tool] = field(default_factory=list)

    # Workspace + session
    cwd: str = field(default_factory=os.getcwd)
    session_id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:16]}")

    # Sandbox + permissions
    sandbox: Optional[Sandbox] = None
    permission_engine: Optional[PermissionEngine] = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT

    # System prompt / loop bounds
    system: str = ""
    max_turns: int = 100
    max_tokens: int = 4096
    temperature: Optional[float] = 0.0

    # OpenAI Responses API reasoning effort (gpt-5.x / o-series). One of
    # ``none|low|medium|high|xhigh`` for gpt-5.3-codex, ``minimal|low|
    # medium|high`` for gpt-5/o-series. ``low`` is recommended for codex
    # coders so reasoning tokens don't consume the whole output budget.
    reasoning_effort: Optional[str] = None

    # Hooks
    hook_runner: Any = None  # avoid import cycle

    # Optional explicit shared-store directory.
    shared_store_dir: Optional[str] = None

    # Optional worktree manager scope.
    worktree_repo: Optional[str] = None

    # Credentials forwarded to the underlying agentspan Agent (vault names).
    credentials: List[str] = field(default_factory=list)

    # Workflow / agent name (must be a valid identifier; Conductor uses it
    # as the workflow definition name). Auto-derived from session_id if unset.
    agent_name: Optional[str] = None

    # Optional callable evaluated by the Agent each turn. Returns True to
    # stop the loop early. Receives the agent execution context dict;
    # typical use: check the SharedStore for a "phase_done" key written by
    # one of the tools (mirrors 100_issue_fixer's contextbook-file gates).
    stop_condition: Optional[Callable[..., bool]] = None


# ── HarnessRuntime ────────────────────────────────────────────────────────


class HarnessRuntime:
    """Top-level entry point. Construct once per session.

    A :class:`HarnessRuntime` is light on its own — most of the work
    happens server-side inside Conductor when ``submit()`` runs. The
    runtime owns:

    * The list of :class:`Tool` instances
    * The :class:`PermissionEngine` and :class:`Sandbox`
    * The :class:`HookRunner`
    * The :class:`SharedStore`, :class:`TaskManager`, optional
      :class:`WorktreeManager` (in-process state shared with subagents)

    These objects are reachable from the tool worker wrappers (built by
    :mod:`.conductor_adapter`) so per-tool sandbox/permission/hook checks
    run on the host process, then the actual ``tool.call()`` runs.
    """

    def __init__(
        self,
        config: HarnessConfig,
        *,
        agent_runtime: Optional[Any] = None,
    ) -> None:
        from .errors import HarnessConfigError

        if not config.model:
            raise HarnessConfigError("HarnessConfig.model is required")

        # The harness's tool wrappers close over in-memory state
        # (PermissionEngine, Sandbox, HookRunner, session_store) that does
        # not survive a process fork. Force Conductor's TaskHandler to use
        # threads instead of processes so workers run in this process and
        # can reach harness state through closures.
        try:
            from agentspan.agents.runtime.worker_manager import (
                _patch_conductor_use_threads_on_windows,
            )
            _patch_conductor_use_threads_on_windows()
        except ImportError:
            pass

        self._config = config
        self._agent_runtime: Optional[Any] = agent_runtime
        self._owns_runtime = agent_runtime is None

        # Tools list — kept as-is; wrapped lazily by build_agent().
        self._tools: List[Tool] = list(config.tools)

        # Permission engine: use provided or default with mode-only policy.
        self._permission = config.permission_engine or PermissionEngine(
            mode=config.permission_mode
        )

        # Per-session content directory (subagent state, snapshots, etc.).
        self._content_dir = _content_dir_for(self._config.session_id)
        os.makedirs(self._content_dir, exist_ok=True)

        # Shared kv store: parent + subagents see the same view.
        shared_dir = config.shared_store_dir or os.path.join(self._content_dir, "shared")
        self._shared_store = SharedStore(shared_dir)

        # Worktree manager (only if a repo is configured).
        self._worktree_manager: Optional[WorktreeManager] = None
        if config.worktree_repo and os.path.isdir(
            os.path.join(config.worktree_repo, ".git")
        ):
            self._worktree_manager = WorktreeManager(config.worktree_repo)

        # Per-session state hung on the ToolUseContext store.
        self._task_manager = TaskManager()
        self._session_store: Dict[str, Any] = {
            "harness": self,
            "task_manager": self._task_manager,
            "content_dir": self._content_dir,
            "shared_store": self._shared_store,
            "shared_store_dir": shared_dir,
        }
        if config.sandbox is not None:
            self._session_store["sandbox"] = config.sandbox
            tasks_dir = os.environ.get("AGENTSPAN_HARNESS_TASKS_DIR") or os.path.join(
                os.path.expanduser("~"), ".agentspan", "harness", "tasks"
            )
            try:
                config.sandbox.add_read_root(tasks_dir)
                config.sandbox.add_read_root(self._content_dir)
            except AttributeError:
                pass
        if self._worktree_manager is not None:
            self._session_store["worktree_manager"] = self._worktree_manager

        self._abort = asyncio.Event()
        self._closed = False
        self._last_execution_id: Optional[str] = None

        # Register as the active harness for our tools so wrapper calls
        # from stale prior worker threads land on this instance instead of
        # a half-closed previous one.
        from .conductor_adapter import _register_active
        _register_active(self)

    # ── Public API ───────────────────────────────────────────────────

    @property
    def config(self) -> HarnessConfig:
        return self._config

    @property
    def session_id(self) -> str:
        return self._config.session_id

    @property
    def cwd(self) -> str:
        return self._config.cwd

    @property
    def session_store(self) -> Dict[str, Any]:
        """Per-session shared state (task_manager, content_dir, shared_store, sandbox)."""
        return self._session_store

    @property
    def permission(self) -> PermissionEngine:
        return self._permission

    @property
    def hook_runner(self) -> Any:
        return self._config.hook_runner

    @property
    def permission_mode_value(self) -> str:
        return self._config.permission_mode.value

    @property
    def abort_event(self) -> asyncio.Event:
        return self._abort

    @property
    def last_execution_id(self) -> Optional[str]:
        return self._last_execution_id

    def abort(self) -> None:
        """Signal in-progress tools and cancel the underlying execution."""
        self._abort.set()
        if self._last_execution_id and self._agent_runtime is not None:
            try:
                self._agent_runtime.terminate(
                    self._last_execution_id, reason="aborted by harness"
                )
            except Exception:  # noqa: BLE001
                logger.exception("terminate failed")

    def submit(self, prompt: str) -> AsyncIterator[Any]:
        """Submit a user prompt. Returns an async iterator of ``AgentEvent``.

        Each event has a ``type`` attribute (``THINKING``, ``MESSAGE``,
        ``TOOL_CALL``, ``TOOL_RESULT``, ``DONE``, ``ERROR``, etc.) and
        carries the ``execution_id`` for correlation across kill/resume.
        """
        return self._submit(prompt)

    async def _submit(self, prompt: str) -> AsyncIterator[Any]:
        from .conductor_adapter import build_agent

        runtime = self._get_or_build_runtime()
        agent = build_agent(harness=self, name=self._derive_agent_name())

        stream = await runtime.stream_async(
            agent, prompt, idempotency_key=self._config.session_id
        )
        # AsyncAgentStream is async-iterable; events flow as they arrive.
        if stream.handle is not None:
            self._last_execution_id = stream.handle.execution_id
            logger.info("harness session %s → execution %s",
                        self._config.session_id, self._last_execution_id)
        async for event in stream:
            yield event

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            from .conductor_adapter import _unregister_active
            _unregister_active(self)
        except Exception:  # noqa: BLE001
            pass
        if self._owns_runtime and self._agent_runtime is not None:
            try:
                self._agent_runtime.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("AgentRuntime shutdown failed")

    def __enter__(self) -> "HarnessRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ── Internals ────────────────────────────────────────────────────

    def _get_or_build_runtime(self) -> Any:
        if self._agent_runtime is not None:
            return self._agent_runtime
        from agentspan.agents import AgentRuntime
        self._agent_runtime = AgentRuntime()
        return self._agent_runtime

    def _derive_agent_name(self) -> str:
        if self._config.agent_name:
            return self._config.agent_name
        # Conductor workflow names allow letters/digits/underscores/hyphens.
        # session_id starts with "sess_" — already valid.
        return f"harness_{self._config.session_id}"


def _content_dir_for(session_id: str) -> str:
    base = os.environ.get("AGENTSPAN_HARNESS_SESSIONS_DIR") or os.path.join(
        os.path.expanduser("~"), ".agentspan", "harness", "sessions"
    )
    return os.path.join(base, session_id + ".content")


__all__ = ["HarnessConfig", "HarnessRuntime"]
