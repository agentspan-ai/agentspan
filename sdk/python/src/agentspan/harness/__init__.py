# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Coding-agent harness — Pythonic toolset + safety wrappers on top of
agentspan ``Agent`` workflows.

A :class:`HarnessRuntime` session **is** an agentspan ``Agent`` execution.
The harness wraps :class:`Tool` instances with permission / sandbox / hook
checks, hands them to an :class:`Agent`, and submits via
:class:`AgentRuntime`. The conversation loop, durability, retries,
telemetry, and per-user credential vault are all owned by Conductor.

Quick start::

    from agentspan.harness import HarnessConfig, HarnessRuntime
    from agentspan.harness.sandbox import ChecksOnlySandbox
    from agentspan.harness.tools.builtins import default_full_tools

    runtime = HarnessRuntime(
        HarnessConfig(
            model="anthropic/claude-sonnet-4-6",
            tools=default_full_tools(),
            cwd="/path/to/repo",
            sandbox=ChecksOnlySandbox(allowed_read_roots=["/path/to/repo"]),
            system="You are a code reviewer.",
        )
    )
    async for event in runtime.submit("Summarize the architecture"):
        print(event.type, event.content)
    runtime.close()

See ``docs/design/CODING_AGENT_HARNESS_DESIGN.md`` for the full design.
"""

from .errors import (
    HarnessConfigError,
    HarnessError,
    HookBlockedError,
    PermissionDeniedError,
    ProviderError,
    SandboxViolationError,
    ToolValidationError,
)
from .events import AgentEvent, EventType, RuntimeEvent
from .runtime import HarnessConfig, HarnessRuntime
from .tasks import TaskManager, TaskState

__all__ = [
    # Runtime
    "HarnessConfig",
    "HarnessRuntime",
    # Tasks
    "TaskManager",
    "TaskState",
    # Events
    "AgentEvent",
    "EventType",
    "RuntimeEvent",
    # Errors
    "HarnessConfigError",
    "HarnessError",
    "HookBlockedError",
    "PermissionDeniedError",
    "ProviderError",
    "SandboxViolationError",
    "ToolValidationError",
]
