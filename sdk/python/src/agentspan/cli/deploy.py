# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI entry point for agent deployment. Called by the Go CLI.

Supports two discovery modes:
  --package <dotted_name>  Import a Python package and scan for Agent instances.
  --path <directory>       Scan .py files in a directory for Agent instances.
"""

import argparse
import json
import sys

from agentspan.agents import deploy


def main():
    parser = argparse.ArgumentParser(description="Deploy agents to AgentSpan server")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", help="Dotted Python package name to scan")
    group.add_argument("--path", help="Directory path to scan for .py files containing agents")
    parser.add_argument("--agents", required=False, help="Comma-separated agent names to deploy")
    args = parser.parse_args()

    # Redirect stdout → stderr during discovery and deploy so that any
    # print() side-effects from user code don't corrupt our JSON output.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    try:
        if args.package:
            import importlib as _importlib
            from agentspan.agents.runtime.discovery import discover_agents
            from agentspan.cli.discover import discover_from_path

            agents = list(discover_agents([args.package]))

            # Supplement with framework agents (OpenAI, LangGraph, etc.)
            # that discover_agents misses (it only finds native Agent instances)
            try:
                module = _importlib.import_module(args.package)
                if hasattr(module, "__path__"):
                    seen = {getattr(a, "name", None) for a in agents}
                    for pkg_path in module.__path__:
                        for fa in discover_from_path(pkg_path):
                            name = getattr(fa, "name", None)
                            if name and name not in seen:
                                agents.append(fa)
                                seen.add(name)
            except Exception:
                pass
        else:
            from agentspan.cli.discover import discover_from_path
            agents = discover_from_path(args.path)
    except Exception as e:
        sys.stdout = real_stdout
        print(f"Discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.agents:
        names = set(n.strip() for n in args.agents.split(",") if n.strip())
        agents = [a for a in agents if a.name in names]

    results = []
    try:
        for agent in agents:
            try:
                infos = deploy(agent)
                if not infos:
                    raise RuntimeError(f"deploy() returned no results for agent '{agent.name}'")
                info = infos[0]
                results.append({
                    "agent_name": info.agent_name,
                    "registered_name": info.registered_name,
                    "success": True,
                    "error": None,
                })
            except Exception as e:
                results.append({
                    "agent_name": agent.name,
                    "registered_name": None,
                    "success": False,
                    "error": str(e),
                })
                print(f"Deploy failed for {agent.name}: {e}", file=sys.stderr)
    finally:
        sys.stdout = real_stdout

    json.dump(results, sys.stdout)


if __name__ == "__main__":
    main()
