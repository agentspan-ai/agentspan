# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Credentials — non-isolated tools using get_credential().

Demonstrates:
    - @tool(isolated=False, credentials=["STRIPE_SECRET_KEY"])
    - get_credential() to access the injected value in-process
    - When to use isolated=False: SDK clients that can't be pickled across
      subprocess boundaries (e.g. existing SDK objects, shared state)
    - CredentialNotFoundError handling for graceful degradation

When to use isolated=False vs isolated=True (default):
    isolated=True  — runs tool in a fresh subprocess; safer (no env bleed between
                     concurrent tasks); use for shell commands, scripts, any new code
    isolated=False — runs tool in the same worker process; use only when the tool
                     holds shared state or uses objects that can't be serialized
                     (e.g. database connection pools, SDK clients initialized at import)

Requirements:
    - Agentspan server running at AGENTSPAN_SERVER_URL
    - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-5.4)
    - STRIPE_SECRET_KEY stored: agentspan credentials set STRIPE_SECRET_KEY <your-stripe-secret-key>
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    CredentialFile,
    CredentialNotFoundError,
    get_credential,
    tool,
)
from settings import settings


@tool(isolated=False, credentials=["STRIPE_SECRET_KEY"])
def get_customer_balance(customer_id: str) -> dict:
    """Look up a Stripe customer's balance.

    Uses get_credential() to retrieve the injected secret in-process.
    """
    try:
        api_key = get_credential("STRIPE_SECRET_KEY")
    except CredentialNotFoundError:
        return {"error": "STRIPE_SECRET_KEY not configured — run: agentspan credentials set STRIPE_SECRET_KEY <your-value>"}
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


@tool(isolated=False, credentials=["STRIPE_SECRET_KEY"])
def list_recent_charges(limit: int = 5) -> dict:
    """List the most recent Stripe charges."""
    try:
        api_key = get_credential("STRIPE_SECRET_KEY")
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


# Example: CredentialFile for kubeconfig (file-based credential)
# Uncomment and add credentials=["KUBECONFIG"] to use:
#
# @tool(isolated=True, credentials=["KUBECONFIG"])  # isolated=True writes the file to temp HOME
# def get_cluster_nodes() -> dict:
#     """List Kubernetes cluster nodes using the injected kubeconfig."""
#     import subprocess
#     result = subprocess.run(["kubectl", "get", "nodes", "-o", "json"],
#                             capture_output=True, text=True)
#     ...


agent = Agent(
    name="billing_agent",
    model=settings.llm_model,
    tools=[get_customer_balance, list_recent_charges],
    credentials=["STRIPE_SECRET_KEY"],
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
        # agentspan deploy --package examples.16b_credentials_non_isolated
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

