# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Context Condensation Stress Test — watch the server condense history 3+ times.

Demonstrates automatic server-side context condensation.  The agent is asked
to research 25 topics.  Each ``fetch_report`` call returns a ~1 500-char
report, so context grows ~430 tokens per exchange.  With a small configured
context window the server condenses the history multiple times during the run.

How condensation appears in server logs (INFO level)::

    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))
    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))
    Condensed conversation from 22 to 12 messages (triggered by proactive (exceeds context window))

If even the condensed history still exceeds the budget you will also see::

    Context still exceeds budget after condensation: ~N tokens estimated vs M input budget ...

Setup to observe 3+ condensations
----------------------------------
Add to ``server/src/main/resources/application.properties`` (or as a JVM arg)::

    # Shrink the effective context window so condensation fires every ~10 tool calls
    agentspan.default-context-window=5000

With the default 128 K window (gpt-4o-mini) the 25 calls won't trigger
condensation — the window is enormous.  The small override forces it.

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY
"""

import textwrap

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agentspan.agents import AgentRuntime

# ---------------------------------------------------------------------------
# Tool: returns a large (~1 500-char) report so context fills up quickly
# ---------------------------------------------------------------------------

_REPORT_BODY = textwrap.dedent("""\
    Overview
    --------
    {topic} is a rapidly evolving field with significant implications across
    industry, academia, and society.  Researchers have published thousands of
    papers exploring both theoretical foundations and practical applications.

    Key Findings
    ------------
    Studies consistently show that {topic} improves outcomes by 30–60 % compared
    to baseline approaches.  The most cited work (Chen et al., 2023) demonstrated
    a 47 % reduction in error rates when applying modern {topic} techniques to
    real-world datasets spanning healthcare, finance, and logistics.

    Challenges
    ----------
    Despite progress, {topic} faces open problems: interpretability, scalability
    to billion-parameter regimes, and equitable access to compute resources.
    Regulatory frameworks are still catching up with the pace of deployment.

    Recent Developments (2024–2025)
    --------------------------------
    New benchmark suites for {topic} were released in Q1 2025, enabling
    apples-to-apples comparisons across research groups.  Industry adoption
    accelerated, with over 400 Fortune 500 companies reporting production
    deployments.  Open-source tooling matured substantially, lowering the
    barrier to entry for small teams.

    Outlook
    -------
    Analysts project the {topic} market will grow at 28 % CAGR through 2030,
    reaching $420 B globally.  Interdisciplinary collaboration — combining
    domain expertise with technical depth — is expected to drive the next wave
    of breakthroughs.
""")  # ~1 450 chars


@tool
def fetch_report(topic: str) -> str:
    """Fetch a detailed research report for the given topic.

    Returns a structured report covering overview, findings, challenges,
    recent developments, and outlook (~1 500 characters).
    """
    return _REPORT_BODY.format(topic=topic)


# ---------------------------------------------------------------------------
# 25 research topics — forces 25 tool calls and substantial context growth
# ---------------------------------------------------------------------------

TOPICS = [
    "machine learning",
    "large language models",
    "retrieval-augmented generation",
    "transformer architectures",
    "reinforcement learning from human feedback",
    "multimodal AI",
    "AI safety and alignment",
    "federated learning",
    "neural architecture search",
    "graph neural networks",
    "diffusion models",
    "AI in drug discovery",
    "autonomous vehicles",
    "AI-assisted code generation",
    "natural language processing",
    "computer vision",
    "AI in climate modelling",
    "robotics and embodied AI",
    "AI ethics and governance",
    "foundation models",
    "AI in financial forecasting",
    "knowledge graphs",
    "AI in education",
    "causal inference with AI",
    "AI-powered cybersecurity",
]

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_react_agent(
    llm,
    tools=[fetch_report],
    name="research_digest_agent",
)

_PROMPT = (
    "You are a research analyst.  For each of the following 25 topics, call "
    "fetch_report exactly once and then write a single sentence summarising "
    "the key insight from the report.  Topics: "
    + ", ".join(TOPICS)
    + ".  Present your final answer as a numbered list."
)

if __name__ == "__main__":
    print("Starting context condensation stress test.")
    print("Watch the Agentspan server logs for 'Condensed conversation' entries.")
    print()

    with AgentRuntime() as runtime:
        result = runtime.run(graph, _PROMPT)

    print(f"\nStatus: {result.status}")
    result.print_result()
