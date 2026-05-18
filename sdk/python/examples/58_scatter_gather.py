# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Scatter-Gather — massive parallel multi-agent orchestration.

Demonstrates:
    - scatter_gather() helper: decompose → fan-out → synthesize
    - 100 sub-agents running in parallel via FORK_JOIN_DYNAMIC
    - Coordinator (gpt-4o) dispatching worker agents (claude-sonnet)
    - Durable execution with automatic retries on transient failures

The coordinator analyzes the input, splits it into 100 independent sub-tasks,
dispatches 100 worker agents in parallel, and synthesizes the results.

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
    - AGENT_SECONDARY_LLM_MODEL=openai/gpt-4o in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, scatter_gather, tool
from settings import settings


# ── Worker tool: simulates a knowledge base lookup ────────────────────


@tool
def search_knowledge_base(query: str) -> dict:
    """Search the knowledge base for information on a topic.

    Args:
        query: The search query.

    Returns:
        Dictionary with search results.
    """
    # In production, this would call a real search API or vector DB
    return {
        "query": query,
        "results": [
            f"Key finding about {query}: widely used in production systems",
            f"Community perspective on {query}: growing ecosystem",
            f"Performance benchmark for {query}: competitive in its niche",
        ],
    }


# ── Worker agent (Claude Sonnet): researches a single country ────────

researcher = Agent(
    name="researcher",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a country analyst. You will be given the name of a country. "
        "Use the search_knowledge_base tool ONCE to research that country, then "
        "immediately write a brief 2-3 sentence profile covering: GDP ranking, "
        "population, primary industries, and one unique fact. "
        "Do NOT call the tool more than once — synthesize from the first result."
    ),
    tools=[search_knowledge_base],
    max_turns=5,
)

# ── Coordinator (gpt-4o-mini): dispatches 100 parallel researchers ───

COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan",
    "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus",
    "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada",
    "Chad", "Chile", "China", "Colombia", "Congo",
    "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Denmark", "Djibouti", "Dominican Republic", "Ecuador", "Egypt",
    "El Salvador", "Estonia", "Ethiopia", "Fiji", "Finland",
    "France", "Gabon", "Georgia", "Germany", "Ghana",
    "Greece", "Guatemala", "Guinea", "Haiti", "Honduras",
    "Hungary", "Iceland", "India", "Indonesia", "Iran",
    "Iraq", "Ireland", "Israel", "Italy", "Jamaica",
    "Japan", "Jordan", "Kazakhstan", "Kenya", "Kuwait",
    "Laos", "Latvia", "Lebanon", "Libya", "Lithuania",
    "Luxembourg", "Madagascar", "Malaysia", "Mali", "Malta",
    "Mexico", "Mongolia", "Morocco", "Mozambique", "Myanmar",
    "Nepal", "Netherlands", "New Zealand", "Nigeria", "North Korea",
    "Norway", "Oman", "Pakistan", "Panama", "Paraguay",
]

country_list = "\n".join(f"{i+1}. {c}" for i, c in enumerate(COUNTRIES))

coordinator = scatter_gather(
    name="coordinator",
    worker=researcher,
    model=settings.secondary_llm_model,  # gpt-4o — needs larger context for 100 results
    instructions=(
        f"You MUST create EXACTLY {len(COUNTRIES)} researcher calls — one per "
        f"country below. Each call should pass just the country name as the "
        f"request. Issue ALL calls in a SINGLE response.\n\n"
        f"Countries:\n{country_list}\n\n"
        f"After all {len(COUNTRIES)} results return, compile a 'Global Country "
        f"Profiles' report organized by continent, with a brief summary table "
        f"at the top showing the top 10 countries by GDP."
    ),
    # Durability: each sub-agent retries up to 3 times on transient failures.
    # If a sub-agent permanently fails, the coordinator still synthesizes
    # partial results (fail_fast=False is the default).
    retry_count=3,
    retry_delay_seconds=5,
    # 10 minutes — 100 parallel sub-agents need time
    timeout_seconds=600,
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = f"Create a comprehensive profile for each of the {len(COUNTRIES)} countries listed."

    print("=" * 70)
    print(f"  Scatter-Gather: {len(COUNTRIES)} Parallel Sub-Agents")
    print("  Coordinator: openai/gpt-4o  |  Workers: anthropic/claude-sonnet")
    print("=" * 70)
    print(f"\nPrompt: {prompt}")
    print(f"Countries: {len(COUNTRIES)}")
    print(f"Dispatching {len(COUNTRIES)} parallel researcher agents...\n")


    with AgentRuntime() as runtime:
        result = runtime.run(coordinator, prompt)
        print("--- Coordinator Result ---")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(coordinator)
        # CLI alternative:
        # agentspan deploy --package examples.58_scatter_gather
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(coordinator)
