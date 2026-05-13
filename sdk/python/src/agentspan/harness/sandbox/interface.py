# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sandbox abstract interface.

Permissions decide whether a model-suggested action is *allowed*; the
sandbox enforces what the process *can actually do*. They are layered
on purpose — a misconfigured permission rule should not be able to
bypass sandbox enforcement, and a sandbox cannot replace the user-
intent semantics permissions express.

v1 ships a checks-only sandbox: path-prefix and command-allowlist
checks performed in-process. It is not a real OS-level sandbox; it
trusts that tools cooperate. The interface accepts a future
``SandboxExecSandbox`` (macOS), ``LandlockSandbox`` (Linux),
``ContainerSandbox`` (Docker/Podman), or ``MicroVMSandbox`` (Firecracker)
without engine changes.

See ``docs/design/CODING_AGENT_HARNESS_DESIGN.md`` §10.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SandboxResult:
    """Result of a sandbox check. ``allowed`` plus optional reason for
    audit. The orchestrator and tool wrappers convert disallowed results
    into tool-result errors.
    """

    allowed: bool
    reason: str = ""

    @classmethod
    def ok(cls) -> "SandboxResult":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str) -> "SandboxResult":
        return cls(allowed=False, reason=reason)


class Sandbox(ABC):
    """Abstract sandbox.

    Tools (or the orchestrator on their behalf) call these check methods
    BEFORE attempting the operation. Implementations should fail closed
    on ambiguity.
    """

    @abstractmethod
    def check_path_read(self, path: str) -> SandboxResult:
        """Can we read this path?"""

    @abstractmethod
    def check_path_write(self, path: str) -> SandboxResult:
        """Can we write/delete this path?"""

    @abstractmethod
    def check_command(self, command: str, *, cwd: Optional[str] = None) -> SandboxResult:
        """Can we execute this shell command?"""

    @abstractmethod
    def check_url(self, url: str) -> SandboxResult:
        """Can we fetch this URL? Used by network-touching tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier for audit logs."""
