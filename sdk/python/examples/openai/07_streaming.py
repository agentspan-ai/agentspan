# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent with Streaming — real-time event streaming.

Demonstrates:
    - Streaming events from an OpenAI agent running on Conductor
    - The runtime.stream() method works identically for foreign agents
    - Events include: thinking, tool_call, tool_result, done

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agents import Agent, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


@function_tool
def search_knowledge_base(query: str) -> str:
    """Search the knowledge base for relevant information."""
    knowledge = {
        "return policy": "Returns accepted within 30 days with receipt. "
                         "Electronics have a 15-day return window.",
        "shipping": "Free shipping on orders over $50. "
                    "Standard delivery: 3-5 business days.",
        "warranty": "All products come with a 1-year manufacturer warranty. "
                    "Extended warranty available for electronics.",
    }
    query_lower = query.lower()
    for key, value in knowledge.items():
        if key in query_lower:
            return value
    return "No relevant information found for your query."


agent = Agent(
    name="support_agent",
    instructions=(
        "You are a customer support agent. Use the knowledge base to answer "
        "questions accurately. If you can't find the answer, say so honestly."
    ),
    model=settings.llm_model,
    tools=[search_knowledge_base],
)

with AgentRuntime() as runtime:
    print("Streaming events:\n")
    for event in runtime.stream(agent, "What's your return policy for electronics?"):
        detail = event.content or event.tool_name or event.output or ""
        print(f"  [{event.type}] {detail}")
    print("\nStream complete.")
