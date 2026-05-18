# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI entry point for agent discovery. Called by the Go CLI.

Supports two modes:
  --package <dotted_name>  Import a Python package and scan for Agent instances.
  --path <directory>       Scan .py files in a directory for Agent instances.
"""

import argparse
import json
import os
import sys

from agentspan.agents.frameworks.serializer import detect_framework


# Directories that should never be scanned during discovery.
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
    ".eggs",
}


def discover_from_path(directory: str) -> list:
    """Scan .py files in *directory* for module-level Agent instances.

    Adds *directory* to sys.path so that inter-file imports within the
    project still work.  Individual files are loaded via
    ``importlib.util.spec_from_file_location`` to avoid module-name
    collisions in ``sys.modules``.

    Stdout is redirected to stderr during imports so that side-effects
    in imported scripts do not corrupt our JSON output on stdout.
    """
    import importlib
    import importlib.util

    from agentspan.agents.agent import Agent

    if not os.path.isdir(directory):
        raise FileNotFoundError(f"directory not found: {directory}")

    # Keep the root directory on sys.path so inter-file imports work
    # (e.g. ``from settings import settings``).
    abs_dir = os.path.abspath(directory)
    if abs_dir not in sys.path:
        sys.path.insert(0, abs_dir)

    seen_names: set = set()
    discovered: list = []

    # Redirect stdout → stderr while importing so print() side-effects
    # don't pollute our JSON output channel.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    try:
        for root, dirs, files in os.walk(abs_dir):
            # Prune directories we should never scan
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS
                and not d.startswith(".")
                and not d.endswith(".egg-info")
            ]

            for fname in sorted(files):
                if not fname.endswith(".py") or fname.startswith("_"):
                    continue

                file_path = os.path.join(root, fname)

                # Build a unique module name from the relative path so that
                # identically-named files in different subdirectories don't
                # collide in sys.modules.
                rel_path = os.path.relpath(file_path, abs_dir)
                mod_name = rel_path[:-3].replace(os.sep, ".")  # e.g. "agents.support"

                if mod_name in sys.modules:
                    mod = sys.modules[mod_name]
                else:
                    spec = importlib.util.spec_from_file_location(mod_name, file_path)
                    if spec is None or spec.loader is None:
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    try:
                        spec.loader.exec_module(mod)
                    except BaseException as e:
                        del sys.modules[mod_name]
                        print(f"Skipping {rel_path}: {e}", file=sys.stderr)
                        continue

                for attr_name in dir(mod):
                    if attr_name.startswith("_"):
                        continue
                    obj = getattr(mod, attr_name, None)
                    if obj is None:
                        continue
                    # Native Agent or framework agent (OpenAI, LangChain, ADK, etc.)
                    is_native = isinstance(obj, Agent)
                    is_framework = (not is_native) and detect_framework(obj) is not None
                    name = getattr(obj, "name", None)
                    if (is_native or is_framework) and name and name not in seen_names:
                        discovered.append(obj)
                        seen_names.add(name)
    finally:
        sys.stdout = real_stdout

    return discovered


def main():
    parser = argparse.ArgumentParser(description="Discover agents in a Python package or directory")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", help="Dotted Python package name to scan")
    group.add_argument("--path", help="Directory path to scan for .py files containing agents")
    args = parser.parse_args()

    try:
        if args.package:
            import importlib as _importlib

            from agentspan.agents.runtime.discovery import discover_agents

            # discover_agents finds native agents
            agents = list(discover_agents([args.package]))

            # Supplement with framework agents that discover_agents may miss.
            # Import the package and scan its on-disk directories with
            # discover_from_path, which detects framework agents too.
            try:
                module = _importlib.import_module(args.package)
                if hasattr(module, "__path__"):
                    seen = {a.name for a in agents}
                    for pkg_path in module.__path__:
                        for fa in discover_from_path(pkg_path):
                            name = getattr(fa, "name", None)
                            if name and name not in seen:
                                agents.append(fa)
                                seen.add(name)
            except Exception:
                pass
        else:
            agents = discover_from_path(args.path)
    except Exception as e:
        print(f"Discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    result = [
        {"name": a.name, "framework": detect_framework(a) or "native"}
        for a in agents
    ]
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
