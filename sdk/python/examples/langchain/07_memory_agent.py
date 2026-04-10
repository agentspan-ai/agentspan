# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Memory Agent — agent with conversational context.

Demonstrates:
    - Using create_agent which handles context natively
    - Stateful conversation where the agent recalls prior exchanges
    - HR assistant with user profile lookup

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def get_user_profile(username: str) -> str:
    """Fetch the profile for a given username.

    Args:
        username: The user's login name.
    """
    profiles = {
        "alice": "Alice Chen, Software Engineer, 5 years experience, Python/Go specialist.",
        "bob": "Bob Martinez, Data Scientist, PhD in Statistics, R/Python expert.",
        "carol": "Carol Williams, Product Manager, 8 years in B2B SaaS.",
    }
    return profiles.get(username.lower(), f"No profile found for '{username}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_user_profile]

graph = create_agent(
    llm,
    tools=tools,
    name="memory_agent",
    system_prompt="You are a helpful HR assistant. Remember information from earlier in the conversation.",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Look up the profile for alice and tell me about her skills.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.07_memory_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
