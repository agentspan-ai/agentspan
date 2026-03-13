# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Introductions — agents introduce themselves before a discussion.

Demonstrates the ``introduction`` parameter on Agent, which adds a
self-introduction to the conversation transcript at the start of
multi-agent group chats (round_robin, random, swarm, manual).

This helps agents understand who they're collaborating with and
establishes context for the discussion.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from settings import settings

# ── Agents with introductions ────────────────────────────────────────

architect = Agent(
    name="architect",
    model=settings.llm_model,
    introduction=(
        "I am the Software Architect. I focus on system design, scalability, "
        "and technical trade-offs. I'll evaluate proposals from an architecture "
        "perspective."
    ),
    instructions=(
        "You are a software architect. Focus on system design, scalability, "
        "and architectural patterns. Keep responses to 2-3 paragraphs."
    ),
)

security_engineer = Agent(
    name="security_engineer",
    model=settings.llm_model,
    introduction=(
        "I am the Security Engineer. I focus on threat modeling, authentication, "
        "authorization, and data protection. I'll flag any security concerns."
    ),
    instructions=(
        "You are a security engineer. Focus on security implications, "
        "vulnerabilities, and best practices. Keep responses to 2-3 paragraphs."
    ),
)

product_manager = Agent(
    name="product_manager",
    model=settings.llm_model,
    introduction=(
        "I am the Product Manager. I focus on user needs, business value, "
        "and delivery timelines. I'll ensure we stay focused on what matters "
        "to customers."
    ),
    instructions=(
        "You are a product manager. Focus on user needs, business value, "
        "and prioritization. Keep responses to 2-3 paragraphs."
    ),
)

# ── Team discussion with introductions ───────────────────────────────

# Introductions are automatically prepended to the conversation transcript
# before the first turn, so each agent knows who's in the room.
design_review = Agent(
    name="design_review",
    model=settings.llm_model,
    agents=[architect, security_engineer, product_manager],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=6,
)

with AgentRuntime() as runtime:
    result = runtime.run(
        design_review,
        "We need to design a new user authentication system for our SaaS platform. "
        "Should we use OAuth 2.0, SAML, or build our own JWT-based system?",
    )
    result.print_result()
