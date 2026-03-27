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

    try:
        if args.package:
            from agentspan.agents.runtime.discovery import discover_agents
            agents = discover_agents([args.package])
        else:
            from agentspan.cli.discover import discover_from_path
            agents = discover_from_path(args.path)
    except Exception as e:
        print(f"Discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.agents:
        names = set(args.agents.split(","))
        agents = [a for a in agents if a.name in names]

    results = []
    for agent in agents:
        try:
            infos = deploy(agent)
            info = infos[0]
            results.append({
                "agent_name": info.agent_name,
                "workflow_name": info.workflow_name,
                "success": True,
                "error": None,
            })
        except Exception as e:
            results.append({
                "agent_name": agent.name,
                "workflow_name": None,
                "success": False,
                "error": str(e),
            })
            print(f"Deploy failed for {agent.name}: {e}", file=sys.stderr)

    json.dump(results, sys.stdout)


if __name__ == "__main__":
    main()
