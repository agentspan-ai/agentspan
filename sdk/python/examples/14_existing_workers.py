# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Existing Workers — use @worker_task functions as agent tools.

Demonstrates:
    - Passing existing @worker_task functions directly as agent tools
    - Mixing @worker_task and @tool functions in a single agent
    - No re-wrapping or boilerplate needed

Requirements:
    - Conductor server with LLM support
    - conductor-python installed (provides @worker_task)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from conductor.client.worker.worker_task import worker_task

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# --- Existing @worker_task functions (already deployed, already working) ---

@worker_task(task_definition_name="get_customer_data")
def get_customer_data(customer_id: str) -> dict:
    """Fetch customer data from the database."""
    # In production this would query a real database
    customers = {
        "C001": {"name": "Alice", "plan": "Enterprise", "since": "2021-03"},
        "C002": {"name": "Bob", "plan": "Starter", "since": "2023-11"},
    }
    return customers.get(customer_id, {"error": "Customer not found"})


@worker_task(task_definition_name="get_order_history")
def get_order_history(customer_id: str, limit: int = 5) -> dict:
    """Retrieve recent order history for a customer."""
    orders = {
        "C001": [
            {"id": "ORD-101", "amount": 250.00, "status": "delivered"},
            {"id": "ORD-098", "amount": 89.99, "status": "delivered"},
        ],
        "C002": [
            {"id": "ORD-110", "amount": 45.00, "status": "shipped"},
        ],
    }
    return {"customer_id": customer_id, "orders": orders.get(customer_id, [])[:limit]}


# --- A new @tool function specific to this agent ---

@tool
def create_support_ticket(customer_id: str, issue: str, priority: str = "medium") -> dict:
    """Create a support ticket for a customer."""
    return {"ticket_id": "TKT-999", "customer_id": customer_id, "issue": issue, "priority": priority}


# --- Agent that mixes both @worker_task and @tool functions ---

agent = Agent(
    name="customer_support",
    model=settings.llm_model,
    tools=[get_customer_data, get_order_history, create_support_ticket],
    instructions=(
        "You are a customer support agent. Use the available tools to look up "
        "customer information, check order history, and create support tickets."
    ),
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Customer C001 is asking about their recent orders. Look them up and summarize.")
    result.print_result()
