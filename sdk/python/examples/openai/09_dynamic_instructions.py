# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent with Dynamic Instructions — callable instruction function.

Demonstrates:
    - Using a callable function for dynamic instructions
    - Instructions that change based on context (time of day, user info, etc.)
    - Function tools alongside dynamic instructions

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from datetime import datetime

from agents import Agent, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


def get_dynamic_instructions(ctx, agent) -> str:
    """Generate instructions based on current context."""
    hour = datetime.now().hour
    if hour < 12:
        greeting_style = "cheerful morning"
        tone = "energetic and upbeat"
    elif hour < 17:
        greeting_style = "professional afternoon"
        tone = "focused and efficient"
    else:
        greeting_style = "relaxed evening"
        tone = "calm and conversational"

    return (
        f"You are a personal assistant with a {greeting_style} style. "
        f"Respond in a {tone} tone. "
        f"Current time: {datetime.now().strftime('%I:%M %p')}. "
        f"Always be helpful and use available tools when appropriate."
    )


@function_tool
def get_todo_list() -> str:
    """Get the user's current todo list."""
    todos = [
        "Review PR #42 — high priority",
        "Write unit tests for auth module",
        "Team standup at 2pm",
        "Deploy v2.1 to staging",
    ]
    return "\n".join(f"- {t}" for t in todos)


@function_tool
def add_todo(task: str, priority: str = "medium") -> str:
    """Add a new item to the todo list."""
    return f"Added to todo list: '{task}' (priority: {priority})"


agent = Agent(
    name="personal_assistant",
    instructions=get_dynamic_instructions,
    model=settings.llm_model,
    tools=[get_todo_list, add_todo],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Show me my todo list and add 'Prepare demo for Friday' as high priority.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.openai.09_dynamic_instructions
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
