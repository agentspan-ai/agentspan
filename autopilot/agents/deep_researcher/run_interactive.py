#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deep Researcher — interactive terminal version.

A simple terminal loop where users submit research topics, see streaming
progress, and receive final reports.

Usage:
    python run_interactive.py

Requirements:
    - Conductor server at AGENTSPAN_SERVER_URL (default http://localhost:6767/api)
    - AGENTSPAN_LLM_MODEL (default openai/gpt-4o)
    - BRAVE_API_KEY (optional — falls back to simulated web search)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the agentspan SDK is importable from the local source tree.
_SDK_SRC = str(Path(__file__).resolve().parent.parent.parent.parent / "sdk" / "python" / "src")
if _SDK_SRC not in sys.path:
    sys.path.insert(0, _SDK_SRC)

os.environ.setdefault("AGENTSPAN_LOG_LEVEL", "WARNING")

from agentspan.agents import Agent, AgentRuntime, EventType, Strategy, tool, wait_for_message_tool

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

LLM_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o")
SECONDARY_LLM_MODEL = os.environ.get("AGENTSPAN_SECONDARY_LLM_MODEL", "openai/gpt-4o")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _brave_search(query: str, count: int = 5) -> list[dict]:
    """Call Brave Search API."""
    import httpx

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
        )
    return results


def _simulated_search(query: str, count: int = 5) -> list[dict]:
    """Placeholder results when no Brave API key is set."""
    return [
        {
            "title": f"Result {i + 1} for: {query}",
            "url": f"https://example.com/search?q={query.replace(' ', '+')}&r={i + 1}",
            "snippet": (
                f"Simulated search result for '{query}'. "
                f"Set BRAVE_API_KEY for live web search."
            ),
        }
        for i in range(count)
    ]


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web for information on a topic. Returns titles, URLs, and snippets."""
    try:
        if BRAVE_API_KEY:
            results = _brave_search(query, count=num_results)
        else:
            results = _simulated_search(query, count=num_results)
    except Exception as exc:
        return f"Search error: {exc}"

    if not results:
        return f"No results found for: {query}"

    lines = []
    for r in results:
        lines.append(f"**{r['title']}**")
        lines.append(f"  URL: {r['url']}")
        lines.append(f"  {r['snippet']}")
        lines.append("")
    return "\n".join(lines)


@tool
def reply_to_user(message: str) -> str:
    """Send your response to the user. Call this when the research is complete."""
    return "ok"


# ---------------------------------------------------------------------------
# Agent builders
# ---------------------------------------------------------------------------


def _build_pipeline_agents():
    """Build the four pipeline agents and return the composed pipeline."""
    planner = Agent(
        name="research_planner",
        model=LLM_MODEL,
        instructions="""\
You are a research planner. Given a research topic, break it down into 3-5
focused sub-questions that together will provide comprehensive coverage.

For each sub-question, briefly explain why it matters.

Output your plan as a numbered list:

1. [Sub-question]
   Why: [Rationale]

2. [Sub-question]
   Why: [Rationale]

Be specific and actionable.
""",
    )

    researcher = Agent(
        name="web_researcher",
        model=SECONDARY_LLM_MODEL,
        instructions="""\
You are a web researcher. You receive a research plan with sub-questions.

For EACH sub-question:
1. Use web_search to find relevant information.
2. Extract key facts, data points, and quotes.
3. Note source URLs.

Compile findings grouped by sub-question with source attribution.
""",
        tools=[web_search],
        max_turns=15,
    )

    analyst = Agent(
        name="analyst",
        model=LLM_MODEL,
        instructions="""\
You are a research analyst. Synthesize raw research findings into coherent analysis:
- Key themes across findings
- Consensus views and contradictions
- Knowledge gaps
- Broader implications

Write in clear, professional prose. Add analytical value.
""",
    )

    report_writer = Agent(
        name="report_writer",
        model=LLM_MODEL,
        instructions="""\
You are a report writer. Produce a polished research report:

# [Topic Title]
## Executive Summary
## Background
## Key Findings
## Analysis
## Conclusion
## Sources

Write in a clear, authoritative tone with specific data.
""",
    )

    return planner >> researcher >> analyst >> report_writer


def build_interactive_agent():
    """Build the interactive deep researcher agent with wait_for_message loop."""
    receive_message = wait_for_message_tool(
        name="wait_for_message",
        description="Wait for the next research topic from the user. Payload has a 'text' field.",
    )

    pipeline = _build_pipeline_agents()

    agent = Agent(
        name="deep_researcher_interactive",
        model=LLM_MODEL,
        tools=[receive_message, reply_to_user],
        agents=[pipeline],
        strategy=Strategy.HANDOFF,
        max_turns=100_000,
        stateful=True,
        instructions="""\
You are an interactive deep research coordinator.

Your workflow:
1. Call wait_for_message to receive a research topic from the user.
2. Delegate the topic to the research pipeline (research_planner >> web_researcher >> analyst >> report_writer).
3. Once the pipeline completes, call reply_to_user with the final report.
4. Return to step 1 to wait for the next topic.

If the user says "quit" or "exit", call reply_to_user with a goodbye message
and stop.
""",
    )

    return agent


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

_SEPARATOR = "-" * 62


def _format_event(event) -> str:
    """Format a stream event for terminal display."""
    etype = event.type
    args = event.args or {}

    if etype == EventType.TOOL_CALL:
        tool_name = event.tool_name or ""

        if tool_name == "reply_to_user":
            msg = args.get("message", "")
            return f"\n{_SEPARATOR}\n{msg}\n"

        if tool_name == "wait_for_message":
            return ""

        if tool_name == "web_search":
            query = args.get("query", "")
            return f"  [search] {query}\n"

        return f"  [{tool_name}] {args}\n"

    if etype == EventType.TOOL_RESULT:
        tool_name = event.tool_name or ""
        if tool_name == "web_search" and event.result:
            # Show truncated search result
            raw = str(event.result)
            if len(raw) > 200:
                raw = raw[:200] + "..."
            return f"  -> {raw}\n"
        return ""

    if etype == EventType.ERROR:
        return f"\n[ERROR] {event.content}\n"

    return ""


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------

def main() -> None:
    search_mode = "Brave API" if BRAVE_API_KEY else "simulated (set BRAVE_API_KEY for live search)"

    print(f"Deep Researcher — Interactive Mode")
    print(f"{'=' * 62}")
    print(f"  Model  : {LLM_MODEL}")
    print(f"  Search : {search_mode}")
    print(f"  Server : {os.environ.get('AGENTSPAN_SERVER_URL', 'http://localhost:6767/api')}")
    print(f"{'=' * 62}")
    print("Type a research topic and press Enter. Type 'quit' to exit.\n")

    agent = build_interactive_agent()

    with AgentRuntime() as runtime:
        handle = runtime.start(
            agent,
            "Begin. Wait for the user's first research topic.",
        )
        execution_id = handle.execution_id
        print(f"  Session: {execution_id}\n")

        # Stream events in background, print formatted output
        import threading

        stop_flag = [False]

        def _stream_events():
            for event in handle.stream():
                if stop_flag[0]:
                    break
                text = _format_event(event)
                if text:
                    sys.stdout.write(text)
                    sys.stdout.flush()

                if event.type == EventType.WAITING:
                    sys.stdout.write(f"\n{'=' * 62}\nReady for next topic.\n\n")
                    sys.stdout.flush()

                if event.type in (EventType.DONE, EventType.ERROR):
                    if event.type == EventType.DONE and event.output:
                        sys.stdout.write(f"\n{event.output}\n")
                        sys.stdout.flush()
                    stop_flag[0] = True
                    break

        stream_thread = threading.Thread(target=_stream_events, daemon=True)
        stream_thread.start()

        try:
            while not stop_flag[0]:
                try:
                    user_input = input("Research topic> ")
                except EOFError:
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit"):
                    print("Stopping...")
                    runtime.send_message(execution_id, {"text": "quit"})
                    handle.stop()
                    break

                print(f"\nResearching: {user_input}")
                print(f"Pipeline: Planner >> Researcher >> Analyst >> Report Writer\n")
                runtime.send_message(execution_id, {"text": user_input})

        except KeyboardInterrupt:
            print("\nInterrupted. Stopping agent...")
            handle.stop()

        stop_flag[0] = True
        stream_thread.join(timeout=5)
        print("Session ended.")


if __name__ == "__main__":
    main()
