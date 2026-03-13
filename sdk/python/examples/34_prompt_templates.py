# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Prompt Templates — reusable, versioned prompts stored on the server.

Demonstrates using Conductor's prompt template system for agent instructions
and user prompts. Templates are created once on the server and referenced
by name — promoting reuse, versioning, and centralized management.

PromptTemplate supports:
    - ``name``: Reference an existing template by name
    - ``variables``: Substitute ``${var}`` placeholders in the template
    - ``version``: Pin to a specific version (None = latest)

Requirements:
    - Conductor server with LLM support
    - Prompt templates created on the server (see setup below)
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, PromptTemplate, tool
from settings import settings

# ── Example 1: Instructions from a template ──────────────────────────
# The system prompt comes from a named template stored on the server.
# Variables are substituted at execution time by the Conductor server.

support_agent = Agent(
    name="support_agent",
    model=settings.llm_model,
    instructions=PromptTemplate(
        "customer-support",
        variables={"company": "Acme Corp", "tone": "friendly and professional"},
    ),
)


# ── Example 2: Template with tools ───────────────────────────────────
# Prompt templates work with tools, structured output, and all other
# agent features — they only change how the system prompt is provided.

@tool
def lookup_order(order_id: str) -> dict:
    """Look up an order by ID."""
    return {"order_id": order_id, "status": "shipped", "eta": "2 days"}


@tool
def lookup_customer(email: str) -> dict:
    """Look up customer details by email."""
    return {"email": email, "name": "Jane Doe", "tier": "premium"}


order_agent = Agent(
    name="order_assistant",
    model=settings.llm_model,
    instructions=PromptTemplate(
        "order-support",
        variables={"max_refund": "$500", "escalation_email": "help@acme.com"},
    ),
    tools=[lookup_order, lookup_customer],
)


# ── Example 3: Pinned template version ───────────────────────────────
# Pin to a specific version for production stability.  New template
# versions can be tested separately before promoting.

stable_agent = Agent(
    name="stable_agent",
    model=settings.llm_model,
    instructions=PromptTemplate("production-prompt", version=3),
)


# ── Example 4: User prompt from a template ───────────────────────────
# The user prompt can also reference a template.  This is resolved
# client-side before execution — useful for standardized query formats.


# ── Setup: Create templates on the server ────────────────────────────
# Templates must exist on the server before agents can reference them.
# You can create them via the Conductor UI, API, or the SDK's prompt client.

def setup_templates(runtime: AgentRuntime):
    """Create sample templates (run once)."""
    prompt_client = runtime._clients.get_prompt_client()

    prompt_client.save_prompt(
        prompt_name="customer-support",
        description="System prompt for customer support agents",
        prompt_template=(
            "You are a ${tone} customer support agent for ${company}. "
            "Help customers with their questions. Be concise and helpful."
        ),
    )

    prompt_client.save_prompt(
        prompt_name="order-support",
        description="System prompt for order support agents",
        prompt_template=(
            "You are an order support specialist. You can look up orders "
            "and customer details. Maximum refund authority: ${max_refund}. "
            "For issues beyond your authority, direct customers to ${escalation_email}."
        ),
    )

    prompt_client.save_prompt(
        prompt_name="production-prompt",
        description="Production-stable system prompt",
        prompt_template="You are a helpful assistant. Answer questions clearly and concisely.",
    )

    prompt_client.save_prompt(
        prompt_name="analysis-request",
        description="Standardized analysis request template",
        prompt_template="Please analyze ${topic} and provide key insights with recommendations.",
    )

    print("Templates created successfully.\n")


# ── Run ──────────────────────────────────────────────────────────────

with AgentRuntime() as runtime:
    # Set up templates (idempotent — safe to run multiple times)
    setup_templates(runtime)

    # --- 1. Template-based instructions ---
    print("=== Support Agent (template instructions) ===")
    result = runtime.run(support_agent, "What are your return policies?")
    result.print_result()

    # --- 2. Template with tools ---
    print("\n=== Order Agent (template + tools) ===")
    result = runtime.run(order_agent, "Can you check order #12345?")
    result.print_result()

    # --- 3. User prompt from a template ---
    print("\n=== User Prompt Template ===")
    result = runtime.run(
        stable_agent,
        PromptTemplate("analysis-request", variables={"topic": "Q4 2025 earnings trends"}),
    )
    result.print_result()
