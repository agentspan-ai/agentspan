# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI entry point for agent discovery. Called by the Go CLI.

Supports two modes:
  --package <dotted_name>  Import a Python package and scan for Agent instances.
  --path <directory>       Scan .py files in a directory for Agent instances.
"""

import argparse
import json
import sys

from agentspan.agents.frameworks.serializer import detect_framework


def discover_from_path(directory: str) -> list:
    """Scan .py files in *directory* for module-level Agent instances.

    Adds *directory* to sys.path so files can be imported, then
    dynamically imports each .py file and collects Agent objects.
    """
    import importlib
    import os

    from agentspan.agents.agent import Agent

    if not os.path.isdir(directory):
        raise FileNotFoundError(f"directory not found: {directory}")

    # Ensure the directory is importable
    abs_dir = os.path.abspath(directory)
    if abs_dir not in sys.path:
        sys.path.insert(0, abs_dir)

    seen_names: set = set()
    discovered: list = []

    for fname in sorted(os.listdir(abs_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        mod_name = fname[:-3]  # strip .py
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            print(f"Skipping {fname}: {e}", file=sys.stderr)
            continue

        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            obj = getattr(mod, attr_name, None)
            if isinstance(obj, Agent) and obj.name not in seen_names:
                discovered.append(obj)
                seen_names.add(obj.name)

    return discovered


def main():
    parser = argparse.ArgumentParser(description="Discover agents in a Python package or directory")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", help="Dotted Python package name to scan")
    group.add_argument("--path", help="Directory path to scan for .py files containing agents")
    args = parser.parse_args()

    try:
        if args.package:
            from agentspan.agents.runtime.discovery import discover_agents
            agents = discover_agents([args.package])
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
