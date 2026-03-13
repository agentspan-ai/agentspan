# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Hierarchical Agents — nested agent teams.

Demonstrates multi-level agent hierarchies where a top-level orchestrator
delegates to team leads, who in turn delegate to specialists.

Structure:
    CEO Agent
    ├── Engineering Lead (handoff)
    │   ├── Backend Developer
    │   └── Frontend Developer
    └── Marketing Lead (handoff)
        ├── Content Writer
        └── SEO Specialist

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, OnTextMention
from settings import settings

# ── Level 3: Individual specialists ─────────────────────────────────

backend_dev = Agent(
    name="backend_dev",
    model=settings.llm_model,
    instructions=(
        "You are a backend developer. You design APIs, databases, and server "
        "architecture. Provide technical recommendations with code examples."
    ),
)

frontend_dev = Agent(
    name="frontend_dev",
    model=settings.llm_model,
    instructions=(
        "You are a frontend developer. You design UI components, user flows, "
        "and client-side architecture. Provide recommendations with code examples."
    ),
)

content_writer = Agent(
    name="content_writer",
    model=settings.llm_model,
    instructions=(
        "You are a content writer. You create blog posts, landing page copy, "
        "and marketing materials. Write engaging, clear content."
    ),
)

seo_specialist = Agent(
    name="seo_specialist",
    model=settings.llm_model,
    instructions=(
        "You are an SEO specialist. You optimize content for search engines, "
        "suggest keywords, and improve page rankings."
    ),
)

# ── Level 2: Team leads (handoff to specialists) ───────────────────

engineering_lead = Agent(
    name="engineering_lead",
    model=settings.llm_model,
    instructions=(
        "You are the engineering lead. Route technical questions to the right "
        "specialist: backend_dev for APIs/databases/servers, "
        "frontend_dev for UI/UX/client-side."
    ),
    agents=[backend_dev, frontend_dev],
    strategy=Strategy.HANDOFF,
)

marketing_lead = Agent(
    name="marketing_lead",
    model=settings.llm_model,
    instructions=(
        "You are the marketing lead. Route marketing questions to the right "
        "specialist: content_writer for blog posts/copy, "
        "seo_specialist for SEO/keywords/rankings."
    ),
    agents=[content_writer, seo_specialist],
    strategy=Strategy.HANDOFF,
)

# ── Level 1: CEO orchestrator (handoff to leads) ───────────────────

ceo = Agent(
    name="ceo",
    model=settings.llm_model,
    instructions=(
        "You are the CEO. Route requests to the right department: "
        "engineering_lead for technical/development questions, "
        "marketing_lead for marketing/content/SEO questions."
    ),
    agents=[engineering_lead, marketing_lead],
    handoffs=[
        OnTextMention(text="engineering_lead", target="engineering_lead"),
        OnTextMention(text="marketing_lead", target="marketing_lead"),
    ],
    strategy=Strategy.SWARM,
)

# ── Run ─────────────────────────────────────────────────────────────

with AgentRuntime() as runtime:
    print("--- Technical question (CEO -> Engineering -> Backend) ---")
    result = runtime.run(ceo, "Design a REST API for a user management system with authentication "
                              "and then come up with a marketing campaign for the system")
    result.print_result()
