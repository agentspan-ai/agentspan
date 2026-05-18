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
import stat
import subprocess
import sys
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
    """Download *url* to *dest* showing a progress bar on stderr."""
    response = urllib.request.urlopen(url)
    total = int(response.headers.get("Content-Length", 0))
    block_size = 64 * 1024
    downloaded = 0
    bar_width = 40

    with open(dest, "wb") as f:
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
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                print(
                    f"\r  [{bar}] {pct:5.1%}  {mb_done:.1f}/{mb_total:.1f} MB",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
    if total > 0:
        print(file=sys.stderr)  # newline after progress bar


def _binary_path() -> str:
    """Return the path where the cached CLI binary lives."""
    name = "agentspan.exe" if platform.system().lower() == "windows" else "agentspan"
    return os.path.join(_CACHE_DIR, name)


def _ensure_binary() -> str:
    """Download the CLI binary if it is not already cached and return its path."""
    path = _binary_path()
    if os.path.isfile(path):
        return path

    os.makedirs(_CACHE_DIR, exist_ok=True)
    os_name = _detect_os()
    arch = _detect_arch()
    url = f"{_S3_BUCKET}/cli/latest/agentspan_{os_name}_{arch}"
    if os_name == "windows":
        url += ".exe"

    print("Downloading Agentspan CLI ...", file=sys.stderr, flush=True)
    _download_with_progress(url, path)
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("Agentspan CLI installed.", file=sys.stderr, flush=True)
    return path


def main() -> None:
    """Entry point for the ``agentspan`` console script."""
    binary = _ensure_binary()
    result = subprocess.run([binary] + sys.argv[1:])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
