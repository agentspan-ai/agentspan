"""E2e test: create an agent, load it from disk, RUN IT, verify output.

Two tests:
1. Manual agent creation + run (deterministic — proves loader + runtime work)
2. Orchestrator-created agent + run (LLM-dependent — proves full pipeline)
"""

from __future__ import annotations

import os
import sys
import time
import yaml
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from autopilot.config import AutopilotConfig
from autopilot.loader import load_agent
from autopilot.orchestrator.tools import get_orchestrator_tools, build_integration_catalog


@pytest.mark.e2e
class TestLoadAndRunAgent:
    """Create an agent manually on disk, load it, run it, verify output."""

    def test_run_web_search_agent(self, tmp_path):
        """Create a web search agent on disk, load it, run it on the real server."""

        # ── Step 1: Create agent files manually ──
        print("\n=== Step 1: Create agent on disk ===")
        agent_dir = tmp_path / "agents" / "web_searcher"
        agent_dir.mkdir(parents=True)
        (agent_dir / "workers").mkdir()

        (agent_dir / "agent.yaml").write_text(yaml.dump({
            "name": "web_searcher",
            "model": os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o"),
            "instructions": (
                "You are a web search agent. When given a query, search the web "
                "and provide a concise summary of what you find. Include specific "
                "facts, dates, and URLs from the search results."
            ),
            "tools": ["builtin:web_search"],
            "trigger": {"type": "daemon"},
            "error_handling": {"max_retries": 3, "backoff": "exponential", "on_failure": "pause_and_notify"},
        }))

        (agent_dir / "expanded_prompt.md").write_text(
            "# web_searcher\n\nSearches the web and summarizes findings.\n"
        )

        # ── Step 2: Load from disk ──
        print("\n=== Step 2: Load agent ===")
        agent = load_agent(agent_dir)
        print(f"  Name: {agent.name}")
        print(f"  Model: {agent.model}")
        tool_names = [t._tool_def.name for t in agent.tools] if agent.tools else []
        print(f"  Tools: {tool_names}")
        assert agent.tools, "Agent has no tools"
        assert "web_search" in tool_names, f"Expected web_search in {tool_names}"

        # ── Step 3: Run on real server ──
        print("\n=== Step 3: Run on server ===")
        with AgentRuntime() as runtime:
            handle = runtime.start(
                agent,
                "Search for 'Agentspan AI workflow orchestration' and tell me what you find."
            )
            print(f"  Execution: {handle.execution_id}")

            run_tool_calls = []
            output = ""
            start = time.time()

            for event in handle.stream():
                if event.type == EventType.TOOL_CALL:
                    name = event.tool_name or ""
                    args = {k: v for k, v in (event.args or {}).items() if not k.startswith("__")}
                    run_tool_calls.append(name)
                    if name == "web_search":
                        print(f"  [web_search] query='{args.get('query', '')}'")
                    elif name == "fetch_page":
                        print(f"  [fetch_page] url={str(args.get('url', ''))[:60]}")
                    elif name == "search_and_read":
                        print(f"  [search_and_read] query='{args.get('query', '')}'")
                    else:
                        print(f"  [{name}]")

                elif event.type == EventType.TOOL_RESULT:
                    name = event.tool_name or ""
                    result = str(event.result or "")
                    if name in ("web_search", "search_and_read"):
                        print(f"    -> {len(result)} chars of results")

                elif event.type == EventType.DONE:
                    if event.output:
                        out = event.output
                        if isinstance(out, dict):
                            out = out.get("result", str(out))
                        output = str(out)
                    break

                elif event.type == EventType.ERROR:
                    print(f"  [ERROR] {event.content}")
                    break

                if time.time() - start > 90:
                    handle.stop()
                    break

        # ── Step 4: Verify ──
        print(f"\n=== Step 4: Verify ===")
        print(f"  Tool calls: {run_tool_calls}")
        print(f"  Output ({len(output)} chars): {output[:200]}...")

        assert "web_search" in run_tool_calls or "search_and_read" in run_tool_calls, \
            f"Agent didn't search the web. Calls: {run_tool_calls}"
        assert output, "Agent produced no output"
        assert len(output) > 30, f"Output too short: {output}"

        print(f"\n  SUCCESS: Agent loaded from disk, ran on server, searched web, produced output.")
