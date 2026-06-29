# Copyright (c) 2025 Agentspan
# Licensed under the MIT License.

"""116 — OCG retrieval via the prebuilt sub-agent.

The main agent delegates retrieval to an OCG (Open Context Graph)
sub-agent: ``ocg_agent()`` returns an ordinary ``Agent`` carrying the
canned retrieval prompt and all seven ``ocg_*`` tools; wrapping it with
``agent_tool()`` exposes it to the main agent's LLM as a single tool.

When the main agent calls it, the sub-agent runs its *own* LLM loop —
it can issue several OCG queries and walk entity neighborhoods — and
returns one synthesized, cited answer. The main agent's
context only ever sees that final answer, not the raw graph payloads.

Choose this shape when retrieval takes judgment (multi-step lookups,
aggregation in two steps, query reformulation). For a single direct
lookup from the main agent's own loop, see
``117_ocg_direct_tools.py``.

OCG is opt-in per agent — nothing is auto-injected, and every OCG tool
binds the instance it talks to (no server-side default): set
``OCG_INSTANCE_URL`` (and optionally ``OCG_CREDENTIAL``, a
credential-store *name*).

Run (from ``sdk/python``)::

    # one-time: store the OCG bearer token in the server's secrets store,
    # e.g. in orkes:  PUT /api/secrets/OCG_PUBLIC_KEY  '"<token>"'

    OCG_INSTANCE_URL=https://test.contextgraph.io \
    OCG_CREDENTIAL=OCG_PUBLIC_KEY \
    uv run python examples/116_ocg_subagent.py

    # against an embedded server (e.g. orkes on 8080), add:
    #   AGENTSPAN_SERVER_URL=http://localhost:8080/api
"""

import os

from conductor.ai.agents import Agent, AgentRuntime, agent_tool
from conductor.ai.agents.ocg import ocg_agent

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")

# Per-tool instance binding — required: every OCG tool binds the instance
# it talks to; there is no server-side default.
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
    retriever = ocg_agent(
        name="ocg_retriever",
        model=MODEL,
        url=OCG_INSTANCE_URL,
        credential=OCG_CREDENTIAL,
    )

    main_agent = Agent(
        name="jira_ocg_subagent",
        model=MODEL,
        instructions=(
            "You answer questions about the team's work. Call your "
            "retrieval tool exactly once, passing the user's full "
            "question — messages and Jira tickets all live "
            "behind it. Its answer is complete: when it returns, write "
            "your final response as a concise brief of what it found, "
            "keeping its citations."
        ),
        tools=[agent_tool(retriever)],
        max_turns=4,
    )

    with AgentRuntime() as runtime:
        result = runtime.run(main_agent, PROMPT)
        result.print_result()


if __name__ == "__main__":
    main()
