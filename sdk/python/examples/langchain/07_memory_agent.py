# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Memory Agent — agent with persistent user profile memory.

Demonstrates:
    - In-memory user profile store keyed by session_id
    - Tools to save and retrieve user preferences
    - Personalized responses based on remembered user data
    - Practical use case: personalized assistant that adapts to each user

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# In-memory user profile store (keyed by user_id)
_user_profiles: dict = {}


@tool
def save_preference(user_id: str, key: str, value: str) -> str:
    """Save a user preference or fact to their profile.

    Args:
        user_id: Unique user identifier.
        key: Preference key (e.g., 'name', 'language', 'timezone').
        value: The value to store.
    """
    if user_id not in _user_profiles:
        _user_profiles[user_id] = {}
    _user_profiles[user_id][key] = value
    return f"Saved preference for user {user_id}: {key} = {value}"


@tool
def get_preference(user_id: str, key: str) -> str:
    """Retrieve a user preference from their profile.

    Args:
        user_id: Unique user identifier.
        key: Preference key to look up.
    """
    profile = _user_profiles.get(user_id, {})
    value = profile.get(key)
    if value is None:
        return f"No preference '{key}' found for user {user_id}"
    return f"User {user_id} preference '{key}': {value}"


@tool
def get_full_profile(user_id: str) -> str:
    """Retrieve all stored preferences for a user."""
    profile = _user_profiles.get(user_id, {})
    if not profile:
        return f"No profile data found for user {user_id}"
    items = "\n".join(f"  {k}: {v}" for k, v in profile.items())
    return f"Profile for {user_id}:\n{items}"


graph = create_agent(
    llm,
    tools=[save_preference, get_preference, get_full_profile],
    name="memory_agent",
)

if __name__ == "__main__":
    user_id = "user-42"

    interactions = [
        f"My user ID is {user_id}. Please save that my name is Jordan and I prefer Python.",
        f"For user {user_id}, also save that my timezone is US/Pacific.",
        f"What do you know about user {user_id}?",
    ]

    with AgentRuntime() as runtime:
        for msg in interactions:
            print(f"\nUser: {msg}")
            result = runtime.run(graph, msg)
            result.print_result()
            print("-" * 60)
