# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool contract — the single abstraction every tool implements.

Every model-facing tool must derive from ``Tool`` and implement at least
``call``. Defaults fail closed: tools are non-concurrency-safe, non-read-only,
non-destructive=False explicitly, and route through the general permission
layer unless they override ``check_permissions``.

See ``docs/design/CODING_AGENT_HARNESS_DESIGN.md`` §5.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

# AssistantMessage was removed when the harness moved to Conductor's
# LLM_CHAT_COMPLETE; the parent_message kwarg on Tool.call now carries
# whatever the caller wants to pass (or None).

# Generic type parameters: input shape, output shape.
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


# ── Tool result ───────────────────────────────────────────────────────────


@dataclass
class ToolResult(Generic[TOutput]):
    """Tool execution result.

    ``output`` is the structured Python value the tool produced. ``content``
    is the model-facing string/JSON the orchestrator places in a
    ToolResultBlock. ``content_ref`` and ``preview`` are set when the tool
    persisted its output to a file (large shell stdout, big search results)
    and only a bounded preview should be in the message.
    """

    output: Optional[TOutput] = None
    content: Any = None
    is_error: bool = False
    error_message: Optional[str] = None
    content_ref: Optional[str] = None
    preview: Optional[str] = None
    # Free-form metadata for hooks/audit; not sent to the model.
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, content: Any, *, output: Optional[TOutput] = None, **kwargs: Any) -> "ToolResult[TOutput]":
        return cls(output=output, content=content, is_error=False, **kwargs)

    @classmethod
    def error(cls, message: str, **kwargs: Any) -> "ToolResult[TOutput]":
        # The model sees ``content`` as the error text — keep it actionable.
        return cls(content=message, is_error=True, error_message=message, **kwargs)


# ── Permission decision ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PermissionResult:
    """Result of a tool-specific permission check.

    A tool's ``check_permissions`` may return one of these shapes; the
    permission engine then folds it into the layered decision pipeline.
    """

    behavior: str  # "allow" | "deny" | "ask" | "passthrough"
    message: str = ""
    reason: str = ""
    updated_input: Optional[Dict[str, Any]] = None


# ── Tool execution context ────────────────────────────────────────────────


@dataclass
class ToolUseContext:
    """Per-tool-call execution context handed to ``Tool.call``.

    The orchestrator builds this from the HarnessRuntime's session state.
    Tools should treat fields as read-only references unless they're
    explicitly the tool's own private state.
    """

    cwd: str
    session_id: str
    abort: asyncio.Event
    permission_mode: str = "default"
    agent_id: Optional[str] = None  # set when running inside a subagent
    # Free-form per-session store; harness components hang state on it.
    store: Dict[str, Any] = field(default_factory=dict)


# ── Tool ABC ──────────────────────────────────────────────────────────────


class Tool(ABC, Generic[TInput, TOutput]):
    """Abstract base for every model-facing tool.

    Subclasses must implement ``name``, ``description``, ``input_schema``,
    and ``call``. Every other method has a safe default. When you want
    parallel-safe semantics, override ``is_concurrency_safe`` to return True.
    """

    # ── Identity ─────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable model-facing tool name. Built-ins use snake_case."""

    @property
    def aliases(self) -> tuple[str, ...]:
        """Alternate names the registry resolves to this tool. Optional."""
        return ()

    # ── Schema + description ─────────────────────────────────────────

    @property
    @abstractmethod
    def description(self) -> str:
        """Plain-English description sent to the model in the tool list."""

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema describing the input. Used by the provider client to
        construct the model's tool definition AND by the orchestrator's
        validator before ``call`` runs."""

    # ── Validation (post-schema, semantic) ───────────────────────────

    async def validate_input(self, input: TInput, context: ToolUseContext) -> Optional[str]:
        """Optional semantic check beyond JSON Schema. Return ``None`` to
        accept; return an error message to reject. The orchestrator turns
        rejection into a tool-result error the model can read.
        """
        return None

    # ── Permissions ──────────────────────────────────────────────────

    async def check_permissions(
        self, input: TInput, context: ToolUseContext
    ) -> PermissionResult:
        """Tool-specific permission check, run BEFORE the engine consults
        global rules. Default is ``passthrough`` — let the engine decide
        from rules + mode + hooks.
        """
        return PermissionResult(behavior="passthrough")

    # ── Execution ────────────────────────────────────────────────────

    @abstractmethod
    async def call(
        self,
        input: TInput,
        context: ToolUseContext,
        parent_message: Any = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> ToolResult[TOutput]:
        """Execute the tool. Should never raise — return a ToolResult.error
        on failure so the model can recover. The orchestrator DOES catch
        exceptions and convert them, but tools that raise lose the chance
        to attach actionable error messages.
        """

    # ── Metadata flags ───────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: TInput) -> bool:
        """True iff the tool has zero side effects given this input."""
        return False

    def is_concurrency_safe(self, input: TInput) -> bool:
        """True iff multiple instances of this tool can run in parallel
        without observable interference. Defaults to False — fail closed.
        """
        return False

    def is_destructive(self, input: TInput) -> bool:
        """True for tools that delete data, kill processes, etc. The
        permission engine treats destructive tools more conservatively.
        """
        return False

    def is_open_world(self, input: TInput) -> bool:
        """True for tools that touch the network or other systems we don't
        control (web fetch, MCP calls). Affects sandbox checks.
        """
        return False

    @property
    def max_result_chars(self) -> int:
        """Cap on inline content size in the model-facing result. Tools
        producing more should write to a file and return a preview.
        """
        return 100_000

    def to_safety_classifier_input(self, input: TInput) -> Any:
        """Optional projection sent to the safety classifier. Default empty
        — only relevant for high-risk tools that override.
        """
        return None
