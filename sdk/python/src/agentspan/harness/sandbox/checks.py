# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Checks-only sandbox — v1 default.

Path-prefix + command-allowlist + URL-allowlist checks performed in-process.
This is NOT a real sandbox — it relies on tools cooperatively asking
before they act. It catches the common mistakes (write outside workspace,
fetch a private host, run an unallowlisted shell command) but does not
contain a malicious tool that bypasses the check.

For v1 SDK users running their own code, this is the right trade-off:
no platform-specific dependencies, no privilege drops, easy to reason
about. Hosted/multi-tenant deployments will swap in a stronger impl
behind the same interface.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from .interface import Sandbox, SandboxResult


@dataclass
class ChecksOnlySandbox(Sandbox):
    """In-process path/command/URL allowlists.

    Construction:

      sandbox = ChecksOnlySandbox(
          allowed_read_roots=["/Users/me/projects/foo", "/tmp/agentspan-cache"],
          allowed_write_roots=["/Users/me/projects/foo"],
          denied_paths=["/Users/me/projects/foo/.env"],
          allowed_commands=["git", "gh", "find", "ls"],
          allowed_url_hosts=["api.github.com"],
      )

    Path checks are realpath-aware: symlinks that point outside the
    allowed roots are rejected. Command checks parse the command with
    shlex and match against the first token (the binary name) plus
    well-known wrappers (``env`` prefixes, ``time``, ``sudo`` is
    rejected outright unless explicitly allowlisted).
    """

    allowed_read_roots: List[str] = field(default_factory=list)
    allowed_write_roots: List[str] = field(default_factory=list)
    denied_paths: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    allowed_url_hosts: List[str] = field(default_factory=list)
    block_private_networks: bool = True

    @property
    def name(self) -> str:
        return "checks-only"

    # ── Mutable allowlist extension ──────────────────────────────────

    def add_read_root(self, path: str) -> None:
        """Append a directory to ``allowed_read_roots`` if not already present.

        Used by ``HarnessRuntime`` to auto-grant read access to its tasks
        and content directories so the model can pull large tool-output
        files via ``read_file``.
        """
        real = os.path.realpath(os.path.abspath(path))
        for existing in self.allowed_read_roots:
            if os.path.realpath(os.path.abspath(existing)) == real:
                return
        self.allowed_read_roots.append(path)

    def add_allowed_command(self, name: str) -> None:
        if name not in self.allowed_commands:
            self.allowed_commands.append(name)

    # ── Paths ────────────────────────────────────────────────────────

    def check_path_read(self, path: str) -> SandboxResult:
        return self._check_path(path, write=False)

    def check_path_write(self, path: str) -> SandboxResult:
        return self._check_path(path, write=True)

    def _check_path(self, path: str, *, write: bool) -> SandboxResult:
        if not path:
            return SandboxResult.deny("empty path")
        try:
            real = os.path.realpath(os.path.abspath(path))
        except OSError as exc:
            return SandboxResult.deny(f"path resolution failed: {exc}")

        # Denied paths take precedence.
        for d in self.denied_paths:
            d_real = os.path.realpath(os.path.abspath(d))
            if real == d_real or real.startswith(d_real + os.sep):
                return SandboxResult.deny(f"path is in denied list: {d}")

        roots = self.allowed_write_roots if write else self.allowed_read_roots
        if not roots:
            # No allowlist configured — fail closed for writes, fail open
            # for reads (common dev case: no roots set, allow reads anywhere).
            return SandboxResult.ok() if not write else SandboxResult.deny(
                "no allowed_write_roots configured; configure ChecksOnlySandbox "
                "with allowed_write_roots=[<workspace>]"
            )

        for root in roots:
            root_real = os.path.realpath(os.path.abspath(root))
            if real == root_real or real.startswith(root_real + os.sep):
                return SandboxResult.ok()

        kind = "write" if write else "read"
        return SandboxResult.deny(
            f"path not under any allowed_{kind}_root: {path} (real={real})"
        )

    # ── Commands ─────────────────────────────────────────────────────

    # Wrapper commands we strip when checking the underlying binary.
    _WRAPPERS = ("env", "time", "nice", "ionice")
    # Always-denied commands. A user can re-enable explicitly via
    # allowed_commands but the default is "no" because their misuse is
    # almost always destructive.
    _ALWAYS_BLOCKED = {"sudo", "doas", "su", "rm", "dd", "mkfs"}

    def check_command(
        self, command: str, *, cwd: Optional[str] = None
    ) -> SandboxResult:
        if not command or not command.strip():
            return SandboxResult.deny("empty command")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            return SandboxResult.deny(f"command parse failed: {exc}")
        if not tokens:
            return SandboxResult.deny("empty command after parse")

        # Strip env-var prefixes (FOO=bar) — common in shell.
        i = 0
        while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
            i += 1
        if i >= len(tokens):
            return SandboxResult.deny("command consists only of env assignments")

        # Strip safe wrappers.
        binary = tokens[i]
        if binary in self._WRAPPERS and i + 1 < len(tokens):
            i += 1
            binary = tokens[i]

        # Resolve to the basename.
        base = os.path.basename(binary)

        if base in self._ALWAYS_BLOCKED and base not in self.allowed_commands:
            return SandboxResult.deny(
                f"command {base!r} is always blocked unless explicitly allowed; "
                "add it to ChecksOnlySandbox.allowed_commands to override"
            )

        if not self.allowed_commands:
            # No allowlist → permissive (dev mode).
            return SandboxResult.ok()

        for allowed in self.allowed_commands:
            if fnmatch.fnmatch(base, allowed) or fnmatch.fnmatch(binary, allowed):
                return SandboxResult.ok()

        return SandboxResult.deny(
            f"command {base!r} not in allowed_commands: {self.allowed_commands}"
        )

    # ── URLs ─────────────────────────────────────────────────────────

    _PRIVATE_HOST_PATTERNS = (
        re.compile(r"^localhost$", re.I),
        re.compile(r"^127\.\d+\.\d+\.\d+$"),
        re.compile(r"^10\.\d+\.\d+\.\d+$"),
        re.compile(r"^192\.168\.\d+\.\d+$"),
        re.compile(r"^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$"),
        re.compile(r"^::1$"),
        re.compile(r"^fc00:", re.I),
        re.compile(r"^fe80:", re.I),
    )

    def check_url(self, url: str) -> SandboxResult:
        if not url:
            return SandboxResult.deny("empty url")
        try:
            parsed = urlparse(url)
        except Exception as exc:  # noqa: BLE001
            return SandboxResult.deny(f"url parse failed: {exc}")

        if parsed.scheme not in ("http", "https"):
            return SandboxResult.deny(
                f"unsupported scheme {parsed.scheme!r}; only http/https allowed"
            )

        host = (parsed.hostname or "").lower()
        if not host:
            return SandboxResult.deny("url missing hostname")

        if self.block_private_networks:
            for pattern in self._PRIVATE_HOST_PATTERNS:
                if pattern.match(host):
                    return SandboxResult.deny(
                        f"private/loopback host {host!r} blocked; "
                        "set ChecksOnlySandbox.block_private_networks=False to permit"
                    )

        if not self.allowed_url_hosts:
            return SandboxResult.ok()

        for pattern in self.allowed_url_hosts:
            if fnmatch.fnmatch(host, pattern):
                return SandboxResult.ok()

        return SandboxResult.deny(
            f"host {host!r} not in allowed_url_hosts: {self.allowed_url_hosts}"
        )
