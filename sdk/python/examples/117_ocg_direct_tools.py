# Copyright (c) 2025 Agentspan
# Licensed under the MIT License.

"""117 — OCG retrieval via a direct tool call (no sub-agent).

The main agent holds the OCG query tool *itself*: ``ocg_tools()``
returns raw ``ToolDef``s that dispatch straight to the server's
``OCG_*`` system tasks, so the main agent's own LLM issues the query
and reads the citations — no sub-agent hop, no second LLM loop.

Compared to ``116_ocg_subagent.py``:

- one LLM round-trip cheaper per lookup — there is no retrieval agent
  spending its own turns;
- the raw (projected, capped) OCG response lands directly in the main
  agent's context, so IT does the reading — fine for a single focused
  query, wasteful when retrieval takes several exploratory calls;
- you own the retrieval prompting: the canned OCG system prompt is the
  sub-agent's, so any query-writing guidance the model needs (specific
  keywords, time bounds, two-step aggregation) belongs in your own
  ``instructions`` here.

This example exposes only ``ocg_query`` (the subset switches turn off
entity/memory tools) — the narrowest possible OCG surface.

Instance binding works exactly as in 116: ``OCG_INSTANCE_URL`` (required) /
``OCG_CREDENTIAL`` env vars.

Run (from ``sdk/python``)::

    OCG_INSTANCE_URL=https://test.contextgraph.io \
    OCG_CREDENTIAL=OCG_PUBLIC_KEY \
    uv run python examples/117_ocg_direct_tools.py

    # against an embedded server (e.g. orkes on 8080), add:
    #   AGENTSPAN_SERVER_URL=http://localhost:8080/api
"""

import os

from conductor.ai.agents import Agent, AgentRuntime
from conductor.ai.agents.ocg import ocg_tools

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")

OCG_INSTANCE_URL = os.environ.get("OCG_INSTANCE_URL") or ""
OCG_CREDENTIAL = os.environ.get("OCG_CREDENTIAL")  # credential-store name, never the key
if not OCG_INSTANCE_URL:
    raise SystemExit("Set OCG_INSTANCE_URL to your OCG instance, e.g. https://test.contextgraph.io")

PROMPT = (
    "Catch me up on 'Improvements to Python SDK -- performance, Feature "
    "parity, logging, metrics etc'. What's the current state, what's "
    "underneath it, and what's been changing in the codebase?"
)


def main() -> None:
    main_agent = Agent(
        name="jira_ocg_direct",
        model=MODEL,
        instructions=(
            "You answer questions about the team's work using ocg_query, "
            "a keyword/embedding retrieval tool (NOT an LLM) over a "
            "knowledge graph of messages and Jira tickets. Query "
            "with specific keywords (ticket titles, component names) — "
            "under ~15 content words, never phrased as a question. At "
            "most one query per topic, 4 total; never repeat or rephrase "
            "a query. When the queries are done, write your final "
            "response: a concise brief synthesized from the citations."
        ),
        max_turns=6,
        tools=ocg_tools(
            url=OCG_INSTANCE_URL,
            credential=OCG_CREDENTIAL,
            query=True,
            entities=False,
            memory=False,
        ),
    )

    with AgentRuntime() as runtime:
        result = runtime.run(main_agent, PROMPT)
        result.print_result()


if __name__ == "__main__":
    main()
