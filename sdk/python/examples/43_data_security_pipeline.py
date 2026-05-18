# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Data Security Pipeline — controlled data flow with redaction.

Demonstrates a sequential pipeline with data flow control where
sensitive information is collected, redacted, and then presented safely:

    collector → validator → responder

- **collector**: Fetches raw user data using tools (includes PII).
- **validator**: Redacts sensitive fields (SSN, balances, email) using tools.
- **responder**: Presents the safe, redacted data to the user.

This pattern enforces a security boundary between data access and
user-facing responses, ensuring PII never reaches the final output.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import json

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ── Data tools ───────────────────────────────────────────────────────

@tool
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


# ── Redaction tools ──────────────────────────────────────────────────

@tool
def redact_sensitive_fields(data: str) -> dict:
    """Redact sensitive fields from data before responding to users.

    Args:
        data: JSON string of user data to redact.

    Returns:
        Dictionary with redacted data.
    """
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


# ── Pipeline agents ─────────────────────────────────────────────────

# Data collector fetches raw user data
collector = Agent(
    name="data_collector",
    model=settings.llm_model,
    instructions=(
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
    instructions=(
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
    instructions=(
        "You are a customer service agent. The previous agent has already "
        "validated and redacted sensitive fields. Present ALL fields from the "
        "validated data: share non-redacted values normally, and for any field "
        "marked ***REDACTED***, state that it is restricted for security reasons. "
        "Do not refuse to answer — the data has already been made safe."
    ),
)

# Sequential pipeline enforces data flow: collect → validate → respond
pipeline = collector >> validator >> responder


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            pipeline,
            "Tell me everything about user U001 including their financial details.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.43_data_security_pipeline
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)

