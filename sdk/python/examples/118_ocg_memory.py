# Copyright (c) 2025 Agentspan
# Licensed under the MIT License.

"""118 — OCG-backed long-term memory with human good/bad feedback links.

Enable memory on an agent and the runtime does two things automatically:

  - BEFORE a run: relevant past memories (scoped to this agent/user) are
    retrieved from OCG and injected into the prompt — no tool call needed.
  - AFTER a run: the conversation is summarized (Claude-style: durable facts,
    not the raw transcript) by a small internal summarizer agent and saved back
    to OCG as a memory.

Feedback is HUMAN-only. Agents never vote. Instead, the runtime hands a
``FeedbackEvent`` — including signed *capability URLs* (good/bad) — to the
agent's ``feedback_sink``. A human (e.g. a support engineer) clicks a link to
mark the memory good or bad; the link skips auth (its signature is the
authorization), so the clicker needs no OCG account. Here the sink just prints
the URLs as they'd appear in a Zendesk ticket comment.

Requires the OCG instance to be started with a feedback-link secret
(``OCG_FEEDBACK_LINK_SECRET``) for the capability URLs to be minted.

Run (from ``sdk/python``)::

    OCG_INSTANCE_URL=https://test.contextgraph.io \
    OCG_TOKEN=<bearer-token> \
    uv run python examples/118_ocg_memory.py

    # against an embedded server, also set AGENTSPAN_SERVER_URL.
"""

import os

from conductor.ai.agents import Agent, AgentRuntime, OCGMemoryStore, SemanticMemory
from conductor.ai.agents.ocg_memory import FeedbackEvent

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

OCG_INSTANCE_URL = os.environ.get("OCG_INSTANCE_URL") or ""
# Unlike the ocg.py retrieval tools (which resolve a credential server-side),
# the memory store calls OCG directly from Python, so it holds the bearer token.
OCG_TOKEN = os.environ.get("OCG_TOKEN")
if not OCG_INSTANCE_URL:
    raise SystemExit("Set OCG_INSTANCE_URL to your OCG instance, e.g. https://test.contextgraph.io")


def zendesk_sink(event: FeedbackEvent) -> None:
    """Deliver the good/bad links to a human. In production this would POST a
    comment to the Zendesk ticket; here we just print what would be sent."""
    print("\n--- would post to Zendesk ticket ---")
    print(f"Saved memory: {event.memory_key}")
    print(f"Summary: {event.summary}")
    if event.good_url:
        print(f"  👍 Was this helpful?  {event.good_url}")
        print(f"  👎 Not helpful:       {event.bad_url}")
    print("------------------------------------\n")


def main() -> None:
    store = OCGMemoryStore(
        url=OCG_INSTANCE_URL,
        agent="agent:support",
        user="user:alice",
        token=OCG_TOKEN,
    )

    agent = Agent(
        name="support",
        model=MODEL,
        instructions=(
            "You are a customer support agent. Use any relevant context from "
            "memory to personalize your answer. A memory labeled [bad] was "
            "flagged by a human — treat it with suspicion."
        ),
        semantic_memory=SemanticMemory(store=store, max_results=5),
        feedback_sink=zendesk_sink,
    )

    with AgentRuntime() as runtime:
        print("--- Turn 1 ---")
        runtime.run(
            agent, "Hi, I'm Alice. I'm on the Enterprise plan and prefer email."
        ).print_result()

        print("\n--- Turn 2 (should recall Alice's plan from memory) ---")
        runtime.run(agent, "What plan am I on again?").print_result()


if __name__ == "__main__":
    main()
