"""Example discovery and dependency checking."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import EXAMPLES_DIR, SUBDIRS, Settings
from .models import Example


def check_dep(import_name: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {import_name}"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _collect_from_dir(
    directory: Path,
    name_prefix: str,
    group_stems: set[str] | None,
    prefixes: list[str],
) -> list[Example]:
    results: list[Example] = []
    for f in sorted(directory.glob("[0-9]*.py")):
        name = f"{name_prefix}{f.stem}" if name_prefix else f.stem
        if group_stems is not None and name not in group_stems:
            continue
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        results.append(Example(name=name, path=f, cwd=directory))
    return results


def discover_examples(
    prefixes: list[str],
    group: str | None = None,
) -> list[Example]:
    settings = Settings()

    # If --group specified, only include those stems
    group_stems: set[str] | None = None
    if group:
        group_stems = settings.get_group(group)
        if not group_stems:
            print(f"  WARNING: group '{group}' is empty or not found in .env.judge")
            return []

    examples = _collect_from_dir(EXAMPLES_DIR, "", group_stems, prefixes)

    # All subdirectories (skip silently if deps unavailable)
    for subdir, import_name in SUBDIRS.items():
        subdir_path = EXAMPLES_DIR / subdir
        if not subdir_path.is_dir() or not check_dep(import_name):
            continue
        examples.extend(_collect_from_dir(subdir_path, f"{subdir}/", group_stems, prefixes))

    return examples
