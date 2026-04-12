"""Local filesystem tools — file and directory operations."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, List

from agentspan.agents import tool


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        The file contents as a string.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    return p.read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: Absolute or relative path to the file.
        content: The text content to write.

    Returns:
        Confirmation message with the path written.
    """
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {p}"


@tool
def list_dir(path: str = ".") -> List[str]:
    """List entries in a directory.

    Args:
        path: Directory path. Defaults to current directory.

    Returns:
        Sorted list of entry names in the directory.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {p}")
    return sorted(entry.name for entry in p.iterdir())


@tool
def find_files(directory: str, pattern: str) -> List[str]:
    """Recursively find files matching a glob pattern.

    Args:
        directory: Root directory to search from.
        pattern: Glob pattern to match (e.g. ``"*.py"``, ``"**/*.yaml"``).

    Returns:
        List of matching file paths relative to the directory.
    """
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    matches: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fnmatch.fnmatch(fname, pattern):
                full = Path(dirpath) / fname
                matches.append(str(full.relative_to(root)))
    return sorted(matches)


@tool
def search_in_files(directory: str, query: str, glob: str = "*.py") -> List[str]:
    """Search for a text pattern in files matching a glob.

    Args:
        directory: Root directory to search from.
        query: Text or substring to search for.
        glob: File glob pattern to filter (default ``"*.py"``).

    Returns:
        List of ``"<file>:<line_number>: <line_text>"`` matches.
    """
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    results: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if not fnmatch.fnmatch(fname, glob):
                continue
            fpath = Path(dirpath) / fname
            try:
                text = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    relpath = fpath.relative_to(root)
                    results.append(f"{relpath}:{lineno}: {line.rstrip()}")
    return results


def get_tools() -> List[Any]:
    """Return all local_fs tools."""
    return [read_file, write_file, list_dir, find_files, search_in_files]
