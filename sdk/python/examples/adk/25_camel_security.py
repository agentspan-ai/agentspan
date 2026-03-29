# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CaMeL-inspired Security Policy Agent — controlled data flow.

Demonstrates:
    - Multi-agent system with security policy enforcement
    - Guardrails to prevent sensitive data leakage
    - Sequential pipeline: collector → validator → responder

Inspired by the Google ADK camel sample which uses CaMeL framework
for secure, controlled LLM agent data flow.

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=google_gemini/gemini-2.0-flash as environment variable
"""

from google.adk.agents import Agent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


def fetch_user_data(user_id: str) -> dict:
    """Fetch user data from the database.

    Args:
        user_id: The user's identifier.

    Returns:
        Dictionary with user information.
    """
    users = {
        "U001": {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "role": "admin",
            "ssn_last4": "1234",
            "account_balance": 15000.00,
        },
        "U002": {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "role": "user",
            "ssn_last4": "5678",
            "account_balance": 3200.00,
        },
    }
    return users.get(user_id, {"error": f"User {user_id} not found"})


def redact_sensitive_fields(data: str) -> dict:
    """Redact sensitive fields from data before responding to users.

    Args:
        data: JSON string of user data to redact.

    Returns:
        Dictionary with redacted data.
    """
    import json

    try:
        parsed = json.loads(data) if isinstance(data, str) else data
    except (json.JSONDecodeError, TypeError):
        return {"error": "Could not parse data for redaction"}

    sensitive_keys = {"ssn_last4", "account_balance", "email"}
    redacted = {}
    for k, v in parsed.items():
        if k in sensitive_keys:
            redacted[k] = "***REDACTED***"
        else:
            redacted[k] = v
    return {"redacted_data": redacted}


# Data collector fetches raw user data
collector = Agent(
    name="data_collector",
    model=settings.llm_model,
    instruction=(
        "You are a data collection agent. When asked about a user, "
        "call fetch_user_data with their ID. Pass the raw data along "
        "to the next agent for security review."
    ),
    tools=[fetch_user_data],
)

# Validator enforces data security policy
validator = Agent(
    name="security_validator",
    model=settings.llm_model,
    instruction=(
        "You are a security validator. Review data for sensitive information "
        "(SSN, account balances, email addresses). Use the redact_sensitive_fields "
        "tool to redact any sensitive data before passing it along. "
        "Only pass redacted data to the next agent."
    ),
    tools=[redact_sensitive_fields],
)

# Responder formats the final answer
responder = Agent(
    name="responder",
    model=settings.llm_model,
    instruction=(
        "You are a customer service agent. Use the validated, redacted data "
        "to answer the user's question. NEVER reveal redacted information. "
        "If data shows ***REDACTED***, explain that the information is "
        "restricted for security reasons."
    ),
)

# Sequential pipeline enforces data flow: collect → validate → respond
pipeline = SequentialAgent(
    name="secure_data_pipeline",
    sub_agents=[collector, validator, responder],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.adk.25_camel_security
        runtime.deploy(pipeline)
        runtime.serve(pipeline)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # pipeline,
        # "Tell me everything about user U001 including their financial details.",
        # )
        # result.print_result()
