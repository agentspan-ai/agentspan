# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Multi-Step Tool Calling — chained lookups and calculations.

The agent has four tools. The prompt requires it to:
1. Look up a customer's account
2. Fetch their recent transactions
3. Calculate the total spend
4. Formulate a final answer using all the data

This shows the agent loop in action: the LLM calls tools one at a
time, feeds each result into the next decision, and stops when it has
enough information to answer.

In the Conductor UI you'll see each tool call as a separate DynamicTask
with clear inputs/outputs, making it easy to trace the reasoning chain.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from typing import List

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


@tool
def lookup_customer(email: str) -> dict:
    """Look up a customer by email address."""
    customers = {
        "alice@example.com": {"id": "CUST-001", "name": "Alice Johnson", "tier": "gold"},
        "bob@example.com": {"id": "CUST-002", "name": "Bob Smith", "tier": "silver"},
    }
    return customers.get(email, {"error": f"No customer found for {email}"})


@tool
def get_transactions(customer_id: str, limit: int) -> dict:
    """Get recent transactions for a customer."""
    transactions = {
        "CUST-001": [
            {"date": "2026-02-15", "amount": 120.00, "merchant": "Cloud Services Inc"},
            {"date": "2026-02-12", "amount": 45.50, "merchant": "Office Supplies Co"},
            {"date": "2026-02-10", "amount": 230.00, "merchant": "Dev Tools Ltd"},
        ],
    }
    txns = transactions.get(customer_id, [])
    return {"customer_id": customer_id, "transactions": txns[:limit]}


@tool
def calculate_total(amounts: List[float]) -> dict:
    """Calculate the sum of a list of amounts."""
    total = sum(amounts)
    return {"total": round(total, 2), "count": len(amounts)}


@tool
def send_summary_email(to: str, subject: str, body: str) -> dict:
    """Send a summary email to a customer."""
    return {"status": "sent", "to": to, "subject": subject}


agent = Agent(
    name="account_analyst",
    model=settings.llm_model,
    tools=[lookup_customer, get_transactions, calculate_total, send_summary_email],
    instructions=(
        "You are an account analyst. When asked about a customer, look them up, "
        "fetch their transactions, calculate the total, and provide a summary. "
        "Use the tools step by step."
    ),
)

with AgentRuntime() as runtime:
    result = runtime.run(
        agent,
        "How much has alice@example.com spent recently? "
        "Get her last 3 transactions and give me the total.",
    )
    result.print_result()
