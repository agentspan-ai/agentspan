# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Thin CLI wrapper — downloads and delegates to the Go ``agentspan`` binary.

When the ``agentspan`` Python package is installed, this module is registered
as a console-script entry point so that ``agentspan <command>`` works from the
shell.  On first invocation the native CLI binary is downloaded from S3 and
cached at ``~/.agentspan/bin/``.
"""

from __future__ import annotations

import os
import platform
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

_S3_BUCKET = "https://agentspan.s3.us-east-2.amazonaws.com"
_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".agentspan", "bin")


def _detect_os() -> str:
    s = platform.system().lower()
    if s in ("linux", "darwin", "windows"):
        return s
    raise RuntimeError(f"Unsupported OS: {platform.system()}")


def _detect_arch() -> str:
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    raise RuntimeError(f"Unsupported architecture: {platform.machine()}")


def _download_with_progress(url: str, dest: str) -> None:
    """Download *url* to *dest* atomically, with a progress bar and friendly errors.

    Writes to a temp file in the destination directory and atomically renames on
    success, so an interrupted/partial download never leaves a corrupt binary at
    *dest* (which would otherwise be cached and executed forever). HTTP/network
    failures are surfaced as clear, actionable messages instead of raw tracebacks.
    """
    try:
        response = urllib.request.urlopen(url, timeout=60)  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                f"No Agentspan CLI binary is published for {_detect_os()}/{_detect_arch()} "
                f"(looked at {url}). Your OS/architecture may be unsupported or the release "
                f"may not be available yet."
            ) from exc
        raise RuntimeError(
            f"Failed to download the Agentspan CLI (HTTP {exc.code}) from {url}."
        ) from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(
            f"Could not reach the Agentspan CLI download server ({url}): {reason}. "
            f"Check your network connection, proxy, or firewall settings."
        ) from exc

    total = int(response.headers.get("Content-Length", 0))
    block_size = 64 * 1024
    downloaded = 0
    bar_width = 40

    dest_dir = os.path.dirname(dest) or "."
    os.makedirs(dest_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dest_dir, prefix=".agentspan-dl-")
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total
                    filled = int(bar_width * pct)
                    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                    print(
                        f"\r  [{bar}] {pct:5.1%}  "
                        f"{downloaded / 1048576:.1f}/{total / 1048576:.1f} MB",
                        end="",
                        file=sys.stderr,
                        flush=True,
                    )
        if total > 0:
            print(file=sys.stderr)  # newline after progress bar
        os.replace(tmp_path, dest)  # atomic on POSIX and Windows
    except BaseException:
        # Any failure (incl. KeyboardInterrupt) \u2014 drop the partial file.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _binary_path() -> str:
    """Return the path where the cached CLI binary lives."""
    name = "agentspan.exe" if platform.system().lower() == "windows" else "agentspan"
    return os.path.join(_CACHE_DIR, name)


def _ensure_binary() -> str:
    """Download the CLI binary if it is not already cached and return its path.

    Set ``AGENTSPAN_FORCE_DOWNLOAD=1`` to force a re-download (e.g. to recover from
    a corrupt cache). A zero-byte cached file is treated as missing.
    """
    path = _binary_path()
    force = os.environ.get("AGENTSPAN_FORCE_DOWNLOAD") == "1"
    if not force and os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    # Drop any stale / zero-byte / corrupt cached binary before re-downloading.
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass

    os.makedirs(_CACHE_DIR, exist_ok=True)
    os_name = _detect_os()
    arch = _detect_arch()
    url = f"{_S3_BUCKET}/cli/latest/agentspan_{os_name}_{arch}"
    if os_name == "windows":
        url += ".exe"

    print("Downloading Agentspan CLI ...", file=sys.stderr, flush=True)
    _download_with_progress(url, path)
    # Execute bits are POSIX-only; on Windows .exe is executable by extension.
    if os_name != "windows":
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("Agentspan CLI installed.", file=sys.stderr, flush=True)
    return path


def main() -> None:
    """Entry point for the ``agentspan`` console script."""
    try:
        binary = _ensure_binary()
    except RuntimeError as exc:
        # Friendly, actionable message instead of a raw traceback.
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run([binary] + sys.argv[1:])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
