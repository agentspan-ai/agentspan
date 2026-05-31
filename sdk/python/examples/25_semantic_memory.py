# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Semantic Memory — long-term memory with similarity-based retrieval.

Demonstrates ``SemanticMemory`` for persisting facts across sessions
and retrieving relevant context based on semantic similarity.

The memory is injected into the agent's system prompt at runtime,
giving the agent access to relevant past knowledge.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings
from agentspan.agents.semantic_memory import SemanticMemory

# ── Build up a knowledge base ────────────────────────────────────────

memory = SemanticMemory(max_results=3)

# Simulate storing facts from previous sessions
memory.add("The customer's name is Alice and she prefers email communication.")
memory.add("Alice's account is on the Enterprise plan since March 2021.")
memory.add("Last interaction: Alice reported a billing discrepancy on invoice #1042.")
memory.add("Alice's preferred language is English.")
memory.add("Company policy: Enterprise customers get priority support with 1-hour SLA.")
memory.add("Alice's timezone is US/Pacific.")

# ── Tool that uses memory for context ────────────────────────────────

@tool
def get_customer_context(query: str) -> str:
    """Retrieve relevant customer context from memory."""
    return memory.get_context(query)

# ── Agent with memory-backed context ─────────────────────────────────

agent = Agent(
    name="memory_agent",
    model=settings.llm_model,
    tools=[get_customer_context],
    instructions=(
        "You are a customer support agent with access to a memory system. "
        "Use the get_customer_context tool to recall relevant information "
        "about the customer before responding. Always personalize your response."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("--- Query 1: Billing question ---")
        result = runtime.run(
            agent,
            "I have a question about my billing — is there an issue with my account?",
        )
        result.print_result()

        print("\n--- Query 2: Plan question ---")
        result2 = runtime.run(
            agent,
            "What plan am I on and when did I sign up?",
        )
        result2.print_result()

        print("\n--- Memory contents ---")
        for entry in memory.list_all():
            print(f"  [{entry.id[:8]}] {entry.content}")

        print(f"\n--- Search for 'billing' ---")
        for result in memory.search("billing invoice"):
            print(f"  → {result}")

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.25_semantic_memory
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

