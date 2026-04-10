# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Chat History — multi-turn conversation with context.

Demonstrates:
    - Using create_agent which handles context natively
    - Tools for fact lookup
    - Running a single-turn query with the agent

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def recall_fact(topic: str) -> str:
    """Retrieve a stored fact about the given topic.

    Args:
        topic: The topic to look up (e.g., 'solar system', 'python').
    """
    facts = {
        "solar system": "The Solar System has 8 planets. Neptune is the farthest from the Sun.",
        "python": "Python was created by Guido van Rossum and first released in 1991.",
        "mars": "Mars is the fourth planet from the Sun and has two moons: Phobos and Deimos.",
        "earth": "Earth is the third planet from the Sun and the only known planet to harbor life.",
    }
    return facts.get(topic.lower(), f"No facts stored for '{topic}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [recall_fact]

graph = create_agent(
    llm,
    tools=tools,
    name="chat_history_agent",
    system_prompt="You are a helpful science assistant. Use tools to look up facts when needed.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Which planet in the solar system is farthest from the Sun?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.06_chat_history
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
