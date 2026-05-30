# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — using get_secret() to read injected secrets in-process.

Demonstrates:
    - @tool(secrets=["STRIPE_SECRET_KEY"])
    - get_secret() to access the injected value via the contextvars accessor
    - CredentialNotFoundError handling for graceful degradation

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - STRIPE_SECRET_KEY stored: agentspan secrets set STRIPE_SECRET_KEY <your-stripe-secret-key>
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    CredentialNotFoundError,
    get_secret,
    tool,
)
from settings import settings


@tool(secrets=["STRIPE_SECRET_KEY"])
def get_customer_balance(customer_id: str) -> dict:
    """Look up a Stripe customer's balance.

    Uses get_secret() to retrieve the injected secret in-process.
    """
    try:
        api_key = get_secret("STRIPE_SECRET_KEY")
    except CredentialNotFoundError:
        return {"error": "STRIPE_SECRET_KEY not configured — run: agentspan secrets set STRIPE_SECRET_KEY <your-value>"}
    import urllib.request
    import json
    import base64

    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/customers/{customer_id}",
        headers={"Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            customer = json.loads(resp.read())
            return {
                "customer_id": customer_id,
                "name": customer.get("name"),
                "balance": customer.get("balance", 0) / 100,  # cents → dollars
                "currency": customer.get("currency", "usd").upper(),
            }
    except urllib.error.HTTPError as e:
        return {"error": f"Stripe API error {e.code}: {e.reason}"}


@tool(secrets=["STRIPE_SECRET_KEY"])
def list_recent_charges(limit: int = 5) -> dict:
    """List the most recent Stripe charges."""
    try:
        api_key = get_secret("STRIPE_SECRET_KEY")
    except CredentialNotFoundError:
        return {"error": "STRIPE_SECRET_KEY not configured"}

    import urllib.request
    import json
    import base64

    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/charges?limit={min(limit, 20)}",
        headers={"Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            charges = data.get("data", [])
            return {
                "charges": [
                    {
                        "id": c["id"],
                        "amount": c["amount"] / 100,
                        "currency": c["currency"].upper(),
                        "status": c["status"],
                        "description": c.get("description"),
                    }
                    for c in charges
                ]
            }
    except urllib.error.HTTPError as e:
        return {"error": f"Stripe API error {e.code}: {e.reason}"}



agent = Agent(
    name="billing_agent",
    model=settings.llm_model,
    tools=[get_customer_balance, list_recent_charges],
    secrets=["STRIPE_SECRET_KEY"],
    instructions=(
        "You are a billing assistant with access to Stripe. "
        "Help users look up customer balances and recent charges."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(agent, "Show me the 3 most recent charges.")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        # CLI alternative:
        # agentspan deploy --package examples.16b_secrets_non_isolated
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

