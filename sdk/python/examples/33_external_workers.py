# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""External Worker Tools — reference workers running in other services.

Demonstrates ``@tool(external=True)`` for referencing Conductor workers that
exist in another repository, service, or language.  The function stub provides
the schema (via type hints) and description (via docstring), but **no local
worker is started** — Conductor dispatches the task to whatever worker is
polling for that task definition name.

This is useful when:
    - Workers are written in Java, Go, or another language
    - Workers run in a separate microservice
    - You want to reuse existing Conductor task definitions without duplicating code

Requirements:
    - Conductor server with LLM support
    - The referenced workers must be running somewhere
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ── Example 1: Basic external worker reference ───────────────────────
# The function stub defines the schema; no implementation needed.
# Conductor dispatches "process_order" tasks to whatever worker is polling.

@tool(external=True)
def process_order(order_id: str, action: str) -> dict:
    """Process a customer order. Actions: refund, cancel, update."""
    ...


# ── Example 2: External worker with approval gate ────────────────────
# Dangerous operations can require human approval before execution.

@tool(external=True, approval_required=True)
def delete_account(user_id: str, reason: str) -> dict:
    """Permanently delete a user account. Requires manager approval."""
    ...


# ── Example 3: Mix local and external tools ──────────────────────────
# Local @tool functions and external references work side-by-side.

@tool
def format_response(data: dict) -> str:
    """Format a data dictionary into a human-readable string."""
    return "\n".join(f"  {k}: {v}" for k, v in data.items())


@tool(external=True)
def get_customer(customer_id: str) -> dict:
    """Look up customer details from the CRM system."""
    ...


@tool(external=True)
def check_inventory(product_id: str, warehouse: str = "default") -> dict:
    """Check product availability in a warehouse."""
    ...


# ── Agent: combines local + external tools ───────────────────────────

support_agent = Agent(
    name="support_agent",
    model=settings.llm_model,
    instructions=(
        "You are a customer support agent. Use the available tools to "
        "look up customers, check inventory, process orders, and format "
        "responses for the customer."
    ),
    tools=[
        format_response,     # Local — runs in this process
        get_customer,        # External — runs in CRM service
        check_inventory,     # External — runs in inventory service
        process_order,       # External — runs in order service
    ],
)


# ── Run ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("=== External Worker Tools ===")
        print("Agent has 1 local tool + 3 external worker references.\n")

        result = runtime.run(
            support_agent,
            "Customer C-1234 wants to cancel order ORD-5678. "
            "Look up the customer, check if we have the product in stock, "
            "and process the cancellation.",
        )
        result.print_result()
