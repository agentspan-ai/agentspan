#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Customer Service — Real-world multi-tool agent pattern from ADK samples.

Mirrors the customer-service ADK sample. A single agent with multiple
domain-specific tools handles customer inquiries end-to-end.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    # ── Domain tools ──────────────────────────────────────────────

    def get_account_details(account_id: str) -> dict:
        """Retrieve account details for a customer."""
        accounts = {
            "ACC-001": {
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "plan": "Premium",
                "balance": 142.50,
                "status": "active",
            },
            "ACC-002": {
                "name": "Bob Martinez",
                "email": "bob@example.com",
                "plan": "Basic",
                "balance": 0.00,
                "status": "active",
            },
        }
        return accounts.get(account_id.upper(), {"error": f"Account {account_id} not found"})

    def get_billing_history(account_id: str, num_months: int = 3) -> dict:
        """Get billing history for an account."""
        history = {
            "ACC-001": [
                {"month": "March 2025", "amount": 49.99, "status": "paid"},
                {"month": "February 2025", "amount": 49.99, "status": "paid"},
                {"month": "January 2025", "amount": 42.50, "status": "paid"},
            ],
        }
        records = history.get(account_id.upper(), [])
        return {"account_id": account_id, "billing_history": records[:num_months]}

    def submit_support_ticket(account_id: str, category: str, description: str) -> dict:
        """Submit a support ticket for a customer issue."""
        valid_categories = ["billing", "technical", "account", "general"]
        if category.lower() not in valid_categories:
            return {"error": f"Invalid category. Must be one of: {valid_categories}"}
        return {
            "ticket_id": "TKT-2025-0042",
            "account_id": account_id,
            "category": category,
            "status": "open",
            "message": f"Ticket created for {category} issue",
        }

    def update_account_plan(account_id: str, new_plan: str) -> dict:
        """Update the subscription plan for an account."""
        plans = {"basic": 19.99, "premium": 49.99, "enterprise": 99.99}
        price = plans.get(new_plan.lower())
        if not price:
            return {"error": f"Invalid plan. Available: {list(plans.keys())}"}
        return {
            "status": "success",
            "account_id": account_id,
            "new_plan": new_plan,
            "new_price": f"${price}/month",
            "effective_date": "Next billing cycle",
        }

    agent = Agent(
        name="customer_service_rep",
        model=settings.llm_model,
        instruction=(
            "You are a customer service representative for CloudServe Inc. "
            "Help customers with account inquiries, billing questions, plan changes, "
            "and support tickets. Always verify the account exists before making changes. "
            "Be professional and empathetic."
        ),
        tools=[get_account_details, get_billing_history, submit_support_ticket, update_account_plan],
    )

    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.16_customer_service
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # agent,
        # "I'm customer ACC-001. Can you check my billing history and tell me my current plan? "
        # "I'm thinking about downgrading to the basic plan.",
        # )
        # print(f"Status: {result.status}")
        # print(f"Output: {result.output}")



if __name__ == "__main__":
    main()
