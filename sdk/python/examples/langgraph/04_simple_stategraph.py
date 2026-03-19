# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Simple query pipeline — validate → refine → answer.

Demonstrates:
    - Using create_agent with a processing tool to build a pipeline
    - System prompt directing multi-step behavior (validate, refine, answer)
    - Server-side LLM orchestration (AI_MODEL task) + Python tool worker

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

SYSTEM_PROMPT = (
    "You are a knowledgeable assistant that follows a two-step process:\n"
    "1. First, use the validate_query tool to clean and validate the user's question.\n"
    "2. Then answer the validated, refined question clearly and concisely.\n"
    "Always call validate_query before answering."
)


@tool
def validate_query(query: str) -> str:
    """Validate and clean the user's query. Returns the cleaned query or a default prompt."""
    cleaned = query.strip()
    if not cleaned:
        return "What can you help me with?"
    # Normalize punctuation
    if not cleaned.endswith("?") and not cleaned.endswith("."):
        cleaned = cleaned + "?"
    return cleaned


graph = create_agent(
    llm,
    tools=[validate_query],
    name="query_pipeline",
    system_prompt=SYSTEM_PROMPT,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Tell me about Python")
        print(f"Status: {result.status}")
        result.print_result()
