"""E2e test: user asks a direct question, orchestrator answers using tools.

Reproduces the bug: user types "what is the latest from cnbc.com" and the
orchestrator responds with nothing — just "Working..." then "Ready for your
next request." The LLM produces a text response instead of using tools.

The orchestrator MUST use web_search (or create an agent that does) to answer
direct questions. It should never give an empty response or a response that
isn't grounded in tool results.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from autopilot.orchestrator.tools import get_orchestrator_tools, build_integration_catalog


@pytest.mark.e2e
class TestDirectQuery:
    """User asks a direct question — orchestrator must answer with real data."""

    def test_whats_latest_from_cnbc(self, tmp_path, monkeypatch):
        """
        User: "what is the latest from cnbc.com"
        Expected: orchestrator searches the web and returns actual headlines.
        NOT expected: empty response, text-only response, or "unable to find".
        """
        monkeypatch.setenv("AUTOPILOT_BASE_DIR", str(tmp_path))
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)

        model = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")

        @tool
        def reply_to_user(message: str) -> str:
            """Send response to user."""
            return "ok"

        orch_tools = get_orchestrator_tools()
        catalog = build_integration_catalog()

        from autopilot.integrations.web_search.tools import get_tools as get_web_tools
        web_tools = get_web_tools()

        agent = Agent(
            name="claw_direct_query_test",
            model=model,
            tools=[reply_to_user] + web_tools + orch_tools,
            max_turns=25,
            instructions=f"""You are the Agentspan Claw orchestrator.

When the user asks a DIRECT QUESTION (not "create an agent"), answer it yourself
using the available tools. You have web_search — USE IT.

For example:
- "what is the latest from cnbc.com" → call web_search("cnbc.com latest news"), 
  then call reply_to_user with the results
- "search for X" → call web_search("X"), then reply_to_user with findings

RULES:
1. For direct questions, call web_search FIRST, then reply_to_user with the results.
2. Do NOT just give a text answer from your training data. USE THE TOOLS.
3. Do NOT create an agent for simple one-off questions. Just search and answer.
4. Your reply MUST contain specific information from the search results.

For agent creation requests ("create an agent that..."), follow the normal creation flow.

Available integrations:
{catalog}
""",
        )

        with AgentRuntime() as runtime:
            handle = runtime.start(agent, "what is the latest from cnbc.com")
            print(f"\n  Execution: {handle.execution_id}")

            tool_calls = []
            reply = ""
            start = time.time()

            for event in handle.stream():
                if event.type == EventType.TOOL_CALL:
                    name = event.tool_name or ""
                    args = {k: v for k, v in (event.args or {}).items() if not k.startswith("__")}
                    tool_calls.append(name)
                    if name == "web_search":
                        print(f"  [web_search] query='{args.get('query', '')}'")
                    elif name == "reply_to_user":
                        reply = args.get("message", "")
                        print(f"  [reply_to_user] {reply[:150]}...")

                elif event.type == EventType.TOOL_RESULT:
                    name = event.tool_name or ""
                    if name == "web_search":
                        print(f"    -> {len(str(event.result))} chars of results")

                elif event.type in (EventType.DONE, EventType.ERROR):
                    if event.type == EventType.DONE and not reply and event.output:
                        # LLM gave text response without calling reply_to_user
                        out = event.output
                        if isinstance(out, dict):
                            out = out.get("result", str(out))
                        reply = str(out)
                    break

                if time.time() - start > 90:
                    handle.stop()
                    break

        print(f"\n  Tool calls: {tool_calls}")
        print(f"  Reply ({len(reply)} chars): {reply[:300]}")

        # The orchestrator MUST have called web_search
        assert "web_search" in tool_calls, (
            f"Orchestrator didn't search the web. Tool calls: {tool_calls}. "
            f"It should have called web_search for 'what is the latest from cnbc.com'"
        )

        # The reply must exist and contain real content
        assert reply, "Orchestrator produced no reply"

        # Output quality check
        from tests.e2e.conftest import assert_output_quality
        assert_output_quality(reply, min_length=100)
