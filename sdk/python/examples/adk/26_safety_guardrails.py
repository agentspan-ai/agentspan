# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Safety Guardrails — global safety enforcement using LLM-as-judge.

Demonstrates:
    - Output guardrails that evaluate every agent response
    - Combining multiple safety checks (PII detection, harmful content)
    - Using sequential pipeline to enforce guardrails

Inspired by the Google ADK safety-plugins sample which uses
BasePlugin for global safety. We use guardrails + sequential agents.

Requirements:
    - pip install google-adk
    - Conductor server
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=google_gemini/gemini-2.0-flash in .env or environment
"""

import re

from google.adk.agents import Agent, SequentialAgent

from agentspan.agents import AgentRuntime

from settings import settings


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
    sanitized = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE REDACTED]", sanitized)
    sanitized = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]", sanitized)
    sanitized = re.sub(
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "[CARD REDACTED]", sanitized)

    return {"sanitized_text": sanitized, "was_modified": sanitized != text}


# Main assistant generates responses
assistant = Agent(
    name="helpful_assistant",
    model=settings.llm_model,
    instruction=(
        "You are a helpful customer service assistant. Answer questions "
        "about account details, contact information, and general inquiries. "
        "When providing information, include relevant details."
    ),
)

# Safety checker scans the response
safety_checker = Agent(
    name="safety_checker",
    model=settings.llm_model,
    instruction=(
        "You are a safety reviewer. Check the previous agent's response "
        "for any PII (emails, phone numbers, SSNs, credit card numbers). "
        "Use check_pii on the response text. If PII is found, use "
        "sanitize_response to clean it. Pass the clean version along."
    ),
    tools=[check_pii, sanitize_response],
)

# Pipeline: generate → check → deliver
safe_pipeline = SequentialAgent(
    name="safe_assistant",
    sub_agents=[assistant, safety_checker],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        safe_pipeline,
        "What are the contact details for our support team? "
        "Include email support@company.com and phone 555-123-4567.",
    )
    result.print_result()
