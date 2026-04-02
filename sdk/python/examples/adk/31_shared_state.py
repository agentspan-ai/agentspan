# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Google ADK Shared State — tools sharing state via ToolContext.

Tools can read and write ``context.state``, a dictionary that persists
across tool calls within the same agent execution.

Requirements:
    - pip install google-adk
    - Conductor server with state support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent
from google.adk.tools import FunctionTool, ToolContext

from agentspan.agents import AgentRuntime

from settings import settings


def add_item(item: str, tool_context: ToolContext) -> dict:
    """Add an item to the shared shopping list.

    Args:
        item: The item to add.
        tool_context: ADK tool context with shared state.

    Returns:
        Dictionary confirming the addition.
    """
    items = tool_context.state.get("shopping_list", [])
    items.append(item)
    tool_context.state["shopping_list"] = items
    return {"added": item, "total_items": len(items)}


def get_list(tool_context: ToolContext) -> dict:
    """Get the current shopping list from shared state.

    Args:
        tool_context: ADK tool context with shared state.

    Returns:
        Dictionary with the current list.
    """
    items = tool_context.state.get("shopping_list", [])
    return {"items": items, "total_items": len(items)}


def clear_list(tool_context: ToolContext) -> dict:
    """Clear the shopping list.

    Args:
        tool_context: ADK tool context with shared state.

    Returns:
        Dictionary confirming the clear.
    """
    tool_context.state["shopping_list"] = []
    return {"status": "cleared"}


agent = Agent(
    name="shopping_assistant",
    model=settings.llm_model,
    instruction=(
        "You help manage a shopping list. Use add_item to add items, "
        "get_list to view the list, and clear_list to reset it."
    ),
    tools=[
        FunctionTool(add_item),
        FunctionTool(get_list),
        FunctionTool(clear_list),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        agent,
        "Add milk, eggs, and bread to my shopping list, then show me the list.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.adk.31_shared_state
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)
