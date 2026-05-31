# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Agent with Instruction Templating — dynamic {variable} injection.

Demonstrates:
    - ADK's instruction templating with {variable} syntax
    - Variables resolved from session state at runtime
    - Agent behavior changes based on injected context

Requirements:
    - pip install google-adk
    - Conductor server with Google Gemini LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def get_user_preferences(user_id: str) -> dict:
    """Look up user preferences.

    Args:
        user_id: The user's ID.

    Returns:
        Dictionary with user preferences.
    """
    users = {
        "user_001": {
            "name": "Alice",
            "language": "English",
            "expertise": "beginner",
            "preferred_format": "bullet points",
        },
        "user_002": {
            "name": "Bob",
            "language": "English",
            "expertise": "advanced",
            "preferred_format": "detailed paragraphs",
        },
    }
    return users.get(user_id, {"name": "Guest", "expertise": "intermediate", "preferred_format": "concise"})


def search_tutorials(topic: str, level: str = "intermediate") -> dict:
    """Search for tutorials matching a topic and skill level.

    Args:
        topic: Tutorial topic to search for.
        level: Skill level — beginner, intermediate, or advanced.

    Returns:
        Dictionary with matching tutorials.
    """
    tutorials = {
        ("python", "beginner"): [
            "Python Basics: Variables and Types",
            "Your First Python Function",
            "Lists and Loops for Beginners",
        ],
        ("python", "advanced"): [
            "Metaclasses and Descriptors",
            "Async IO Deep Dive",
            "CPython Internals",
        ],
    }
    results = tutorials.get((topic.lower(), level.lower()), [f"General {topic} tutorial"])
    return {"topic": topic, "level": level, "tutorials": results}


# Agent with templated instructions — {user_name} and {expertise_level}
# get replaced from session state when the agent runs.
agent = Agent(
    name="adaptive_tutor",
    model=settings.llm_model,
    instruction=(
        "You are a personalized programming tutor. "
        "The current user is {user_name} with {expertise_level} expertise. "
        "Adapt your explanations to their level. "
        "Use the search_tutorials tool to find appropriate learning resources."
    ),
    tools=[get_user_preferences, search_tutorials],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "I want to learn Python. What tutorials do you recommend?",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.08_instruction_templating
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
