# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Server auto-start — detect and launch the Agentspan runtime server.

Called during :class:`AgentRuntime` initialisation when the target server
URL points to localhost and is not yet responding.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx


def _log(msg: str) -> None:
    """Print a visible status message to stderr."""
    print(f"[agentspan] {msg}", file=sys.stderr, flush=True)


def _is_localhost(server_url: str) -> bool:
    """Return ``True`` if *server_url* points to a loopback address."""
    host = (urlparse(server_url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _is_server_ready(server_url: str, timeout: float = 2.0) -> bool:
    """Return ``True`` if the server responds to a health check."""
    try:
        base = server_url.rstrip("/")
        # Strip /api suffix if present for the health endpoint
        if base.endswith("/api"):
            base = base[: -len("/api")]
        resp = httpx.get(f"{base}/health", timeout=timeout)
        return resp.status_code < 500
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException, OSError):
        return False


def _find_or_install_cli() -> str | None:
    """Locate the ``agentspan`` CLI binary, installing it if necessary."""
    # 1. Already on $PATH (system install, Homebrew, npm, etc.)
    path = shutil.which("agentspan")
    if path is not None:
        return path

    # 2. Cached binary from a previous download
    try:
        from agentspan.cli import _binary_path

        candidate = _binary_path()
        if os.path.isfile(candidate):
            return candidate
    except Exception:
        pass

    # 3. Not found anywhere — download it now
    try:
        from agentspan.cli import _ensure_binary

        _log("Agentspan CLI not found. Installing...")
        binary = _ensure_binary()
        _log(f"Agentspan CLI installed at {binary}")
        return binary
    except Exception as exc:
        _log(f"Failed to install Agentspan CLI: {exc}")
        return None


def ensure_server_running(server_url: str, *, max_wait: float = 60.0) -> None:
    """Start the Agentspan server if it is not already running.

    Only attempts to start the server when *server_url* points to localhost.
    If the CLI binary cannot be found or installed, a warning is printed but
    no exception is raised — the caller can still proceed (and will fail
    later with a connection error).

    Raises:
        RuntimeError: If the server does not become ready within *max_wait*
            seconds after the start command is issued.
    """
    if not server_url:
        return
    if not _is_localhost(server_url):
        return
    if _is_server_ready(server_url):
        return

    _log(f"Agentspan server is not running at {server_url}.")

    cli = _find_or_install_cli()
    if cli is None:
        _log(
            "Could not find or install the Agentspan CLI. "
            "Please start the server manually with: agentspan server start"
        )
        return

    _log("Starting Agentspan server...")

    try:
        result = subprocess.run(
            [cli, "server", "start"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or "").strip()
            _log(f"Failed to start Agentspan server: {error_msg}")
            if "java" in error_msg.lower() or "jdk" in error_msg.lower():
                _log("The Agentspan server requires Java 21+. Install: https://adoptium.net/")
            _log("Run 'agentspan doctor' for full diagnostics.")
            return
    except OSError as exc:
        _log(f"Failed to start Agentspan server: {exc}")
        return

    # Poll until the server is ready.
    _log("Waiting for server to be ready...")
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if _is_server_ready(server_url):
            _log("Agentspan server is ready.")
            return
        time.sleep(1.0)

    raise RuntimeError(
        f"Agentspan server did not become ready at {server_url} "
        f"within {max_wait:.0f} seconds. "
        f"Check 'agentspan server logs' for details, "
        f"or run 'agentspan doctor' for full diagnostics."
    )
