# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Safety Guardrails Pipeline — PII detection and sanitization.

Demonstrates a sequential pipeline where a safety checker agent scans
the primary agent's output for PII and sanitizes it before delivery:

    assistant → safety_checker

- **assistant**: A helpful agent that answers questions (may include PII).
- **safety_checker**: Scans the response for PII (emails, phones, SSNs,
  credit cards) using regex-based tools and sanitizes any matches.

This pattern uses tool-based PII detection rather than the built-in
guardrail system, showing how sequential agents can enforce safety
policies through explicit scanning and redaction.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

import re

from agentspan.agents import Agent, AgentRuntime, tool
from settings import settings


# ── Safety tools ─────────────────────────────────────────────────────

@tool
def check_pii(text: str) -> dict:
    """Check text for personally identifiable information (PII).

    Args:
        text: The text to scan for PII.

    Returns:
        Dictionary with PII detection results.
    """
    patterns = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    }

    found = {}
    for pii_type, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            found[pii_type] = len(matches)

    return {
        "has_pii": len(found) > 0,
        "pii_types": found,
        "text_length": len(text),
    }


@tool
def sanitize_response(text: str, pii_types: str = "") -> dict:
    """Remove or mask PII from a response before delivering to user.

    Args:
        text: The response text to sanitize.
        pii_types: Comma-separated PII types detected.

    Returns:
        Dictionary with sanitized text.
    """
    sanitized = text
    # Mask common PII patterns
    sanitized = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "[EMAIL REDACTED]", sanitized)
    sanitized = re.sub(
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "[PHONE REDACTED]", sanitized)
    sanitized = re.sub(
        r"\b\d{3}-\d{2}-\d{4}\b",
        "[SSN REDACTED]", sanitized)
    sanitized = re.sub(
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "[CARD REDACTED]", sanitized)

    return {"sanitized_text": sanitized, "was_modified": sanitized != text}


# ── Pipeline agents ─────────────────────────────────────────────────

# Main assistant generates responses
assistant = Agent(
    name="helpful_assistant",
    model=settings.llm_model,
    instructions=(
        "You are a helpful customer service assistant. Answer questions "
        "about account details, contact information, and general inquiries. "
        "When providing information, include relevant details."
    ),
)

# Safety checker scans the response for PII
safety_checker = Agent(
    name="safety_checker",
    model=settings.llm_model,
    instructions=(
        "You are a safety reviewer. Check the previous agent's response "
        "for any PII (emails, phone numbers, SSNs, credit card numbers). "
        "Use check_pii on the response text. If PII is found, use "
        "sanitize_response to clean it. Output only the sanitized version."
    ),
    tools=[check_pii, sanitize_response],
)

# Pipeline: generate → check and sanitize
pipeline = assistant >> safety_checker


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            pipeline,
            "What are the contact details for our support team? "
            "Include email support@company.com and phone 555-123-4567.",
        )
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.44_safety_guardrails
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(pipeline)

