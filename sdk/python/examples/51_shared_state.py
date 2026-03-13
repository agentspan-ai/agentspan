# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Shared State — tools sharing state across calls via ToolContext.

Tools can read and write to ``context.state``, a dictionary that persists
across all tool calls within the same agent execution. This enables
tools to accumulate data, maintain counters, or pass information between
different tool invocations without relying on the LLM to relay state.

Requirements:
    - Conductor server with state support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool
from agentspan.agents.tool import ToolContext
from settings import settings


@tool
def add_item(item: str, context: ToolContext = None) -> dict:
    """Add an item to the shared shopping list.

    Args:
        item: The item to add.
        context: Injected tool context with shared state.

    Returns:
        Dictionary confirming the addition.
    """
    items = context.state.get("shopping_list", [])
    items.append(item)
    context.state["shopping_list"] = items
    return {"added": item, "total_items": len(items)}


@tool
def get_list(context: ToolContext = None) -> dict:
    """Get the current shopping list from shared state.

    Args:
        context: Injected tool context with shared state.

    Returns:
        Dictionary with the current list.
    """
    items = context.state.get("shopping_list", [])
    return {"items": items, "total_items": len(items)}


@tool
def clear_list(context: ToolContext = None) -> dict:
    """Clear the shopping list.

    Args:
        context: Injected tool context with shared state.

    Returns:
        Dictionary confirming the clear.
    """
    context.state["shopping_list"] = []
    return {"status": "cleared"}


agent = Agent(
    name="shopping_assistant_51",
    model=settings.llm_model,
    instructions=(
        "You help manage a shopping list. Use add_item to add items, "
        "get_list to view the list, and clear_list to reset it. "
        "IMPORTANT: Always add all items first, then call get_list separately "
        "in a follow-up step to verify the list contents. Never call get_list "
        "in the same batch as add_item calls."
    ),
    tools=[add_item, get_list, clear_list],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "Add milk, eggs, and bread to my shopping list, then show me the list.",
    )
    result.print_result()
