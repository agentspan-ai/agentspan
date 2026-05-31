#!/usr/bin/env python3
"""Dump serialized AgentConfig JSON for key examples.

Writes each to _configs/{example_name}.json for cross-SDK comparison.

Usage:
    cd sdk/python && uv run python examples/dump_agent_configs.py
"""

from __future__ import annotations

import json
import os
import sys

# Ensure the examples directory is on the path for settings import
sys.path.insert(0, os.path.dirname(__file__))
# Force a consistent model name so both SDKs produce identical values
os.environ["AGENTSPAN_LLM_MODEL"] = "openai/gpt-4o-mini"
os.environ["AGENTSPAN_SECONDARY_LLM_MODEL"] = "openai/gpt-4o"

from agentspan.agents.config_serializer import AgentConfigSerializer

serializer = AgentConfigSerializer()

# Output directory
OUT_DIR = os.path.join(os.path.dirname(__file__), "_configs")
os.makedirs(OUT_DIR, exist_ok=True)


def dump(name: str, agent) -> None:
    """Serialize an agent and write to _configs/{name}.json."""
    try:
        config = serializer.serialize(agent)
        path = os.path.join(OUT_DIR, f"{name}.json")
        with open(path, "w") as f:
            json.dump(config, f, indent=2, sort_keys=True, default=str)
        print(f"  [OK] {name}")
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")


# ── 01_basic_agent ───────────────────────────────────────────────────
def dump_01():
    from agentspan.agents import Agent
    from settings import settings

    agent = Agent(name="greeter", model=settings.llm_model)
    dump("01_basic_agent", agent)


# ── 02_tools ─────────────────────────────────────────────────────────
def dump_02():
    from agentspan.agents import Agent, tool
    from settings import settings

    @tool
    def get_weather(city: str) -> dict:
        """Get current weather for a city."""
        return {}

    @tool
    def calculate(expression: str) -> dict:
        """Evaluate a math expression."""
        return {}

    @tool(approval_required=True, timeout_seconds=60)
    def send_email(to: str, subject: str, body: str) -> dict:
        """Send an email."""
        return {}

    agent = Agent(
        name="tool_demo_agent",
        model=settings.llm_model,
        tools=[get_weather, calculate, send_email],
        instructions="You are a helpful assistant with access to weather, calculator, and email tools.",
    )
    dump("02_tools", agent)


# ── 03_structured_output ─────────────────────────────────────────────
def dump_03():
    from pydantic import BaseModel

    from agentspan.agents import Agent, tool
    from settings import settings

    class WeatherReport(BaseModel):
        city: str
        temperature: float
        condition: str
        recommendation: str

    @tool
    def get_weather(city: str) -> dict:
        """Get current weather data for a city."""
        return {}

    agent = Agent(
        name="weather_reporter",
        model=settings.llm_model,
        tools=[get_weather],
        output_type=WeatherReport,
        instructions="You are a weather reporter. Get the weather and provide a recommendation.",
    )
    dump("03_structured_output", agent)


# ── 05_handoffs ──────────────────────────────────────────────────────
def dump_05():
    from agentspan.agents import Agent, Strategy, tool
    from settings import settings

    @tool
    def check_balance(account_id: str) -> dict:
        """Check the balance of a bank account."""
        return {}

    @tool
    def lookup_order(order_id: str) -> dict:
        """Look up the status of an order."""
        return {}

    @tool
    def get_pricing(product: str) -> dict:
        """Get pricing information for a product."""
        return {}

    billing_agent = Agent(
        name="billing",
        model=settings.llm_model,
        instructions="You handle billing questions: balances, payments, invoices.",
        tools=[check_balance],
    )
    technical_agent = Agent(
        name="technical",
        model=settings.llm_model,
        instructions="You handle technical questions: order status, shipping, returns.",
        tools=[lookup_order],
    )
    sales_agent = Agent(
        name="sales",
        model=settings.llm_model,
        instructions="You handle sales questions: pricing, products, promotions.",
        tools=[get_pricing],
    )

    support = Agent(
        name="support",
        model=settings.llm_model,
        instructions="Route customer requests to the right specialist: billing, technical, or sales.",
        agents=[billing_agent, technical_agent, sales_agent],
        strategy=Strategy.HANDOFF,
    )
    dump("05_handoffs", support)


# ── 06_sequential_pipeline ───────────────────────────────────────────
def dump_06():
    from agentspan.agents import Agent
    from settings import settings

    researcher = Agent(
        name="researcher",
        model=settings.llm_model,
        instructions=(
            "You are a researcher. Given a topic, provide key facts and data points. "
            "Be thorough but concise. Output raw research findings."
        ),
    )
    writer = Agent(
        name="writer",
        model=settings.llm_model,
        instructions=(
            "You are a writer. Take research findings and write a clear, engaging "
            "article. Use headers and bullet points where appropriate."
        ),
    )
    editor = Agent(
        name="editor",
        model=settings.llm_model,
        instructions=(
            "You are an editor. Review the article for clarity, grammar, and tone. "
            "Make improvements and output the final polished version."
        ),
    )
    pipeline = researcher >> writer >> editor
    dump("06_sequential_pipeline", pipeline)


# ── 07_parallel_agents ───────────────────────────────────────────────
def dump_07():
    from agentspan.agents import Agent, Strategy
    from settings import settings

    market_analyst = Agent(
        name="market_analyst",
        model=settings.llm_model,
        instructions=(
            "You are a market analyst. Analyze the given topic from a market perspective: "
            "market size, growth trends, key players, and opportunities."
        ),
    )
    risk_analyst = Agent(
        name="risk_analyst",
        model=settings.llm_model,
        instructions=(
            "You are a risk analyst. Analyze the given topic for risks: "
            "regulatory risks, technical risks, competitive threats, and mitigation strategies."
        ),
    )
    compliance_checker = Agent(
        name="compliance",
        model=settings.llm_model,
        instructions=(
            "You are a compliance specialist. Check the given topic for compliance considerations: "
            "data privacy, regulatory requirements, and industry standards."
        ),
    )
    analysis = Agent(
        name="analysis",
        model=settings.llm_model,
        agents=[market_analyst, risk_analyst, compliance_checker],
        strategy=Strategy.PARALLEL,
    )
    dump("07_parallel_agents", analysis)


# ── 08_router_agent ──────────────────────────────────────────────────
def dump_08():
    from agentspan.agents import Agent, Strategy
    from settings import settings

    planner = Agent(
        name="planner",
        model=settings.llm_model,
        instructions="You create implementation plans. Break down tasks into clear numbered steps.",
    )
    coder = Agent(
        name="coder",
        model=settings.llm_model,
        instructions="You write code. Output clean, well-documented Python code.",
    )
    reviewer = Agent(
        name="reviewer",
        model=settings.llm_model,
        instructions="You review code. Check for bugs, style issues, and suggest improvements.",
    )
    team = Agent(
        name="dev_team",
        model=settings.llm_model,
        instructions=(
            "You are the tech lead. Route requests to the right team member: "
            "planner for design/architecture, coder for implementation, "
            "reviewer for code review."
        ),
        agents=[planner, coder, reviewer],
        strategy=Strategy.ROUTER,
        router=planner,
    )
    dump("08_router_agent", team)


# ── 10_guardrails ────────────────────────────────────────────────────
def dump_10():
    import re

    from agentspan.agents import Agent, Guardrail, GuardrailResult, OnFail, Position, guardrail, tool
    from settings import settings

    @tool
    def get_order_status(order_id: str) -> dict:
        """Look up the current status of an order."""
        return {}

    @tool
    def get_customer_info(customer_id: str) -> dict:
        """Retrieve customer details including payment info on file."""
        return {}

    @guardrail
    def no_pii(content: str) -> GuardrailResult:
        """Reject responses that contain credit card numbers or SSNs."""
        cc_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
        ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
        if re.search(cc_pattern, content) or re.search(ssn_pattern, content):
            return GuardrailResult(
                passed=False,
                message="Your response contains PII. Redact it.",
            )
        return GuardrailResult(passed=True)

    agent = Agent(
        name="support_agent",
        model=settings.llm_model,
        tools=[get_order_status, get_customer_info],
        instructions=(
            "You are a customer support assistant. Use the available tools to "
            "answer questions about orders and customers. Always include all "
            "details from the tool results in your response."
        ),
        guardrails=[
            Guardrail(no_pii, position=Position.OUTPUT, on_fail=OnFail.RETRY),
        ],
    )
    dump("10_guardrails", agent)


# ── 13_hierarchical_agents ───────────────────────────────────────────
def dump_13():
    from agentspan.agents import Agent, Strategy, OnTextMention
    from settings import settings

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
    dump("13_hierarchical_agents", ceo)


# ── 17_swarm_orchestration ───────────────────────────────────────────
def dump_17():
    from agentspan.agents import Agent, Strategy
    from agentspan.agents.handoff import OnTextMention
    from settings import settings

    refund_agent = Agent(
        name="refund_specialist",
        model=settings.llm_model,
        instructions=(
            "You are a refund specialist. Process the customer's refund request. "
            "Check eligibility, confirm the refund amount, and let them know the "
            "timeline. Be empathetic and clear. Do NOT ask follow-up questions -- "
            "just process the refund based on what the customer told you."
        ),
    )
    tech_agent = Agent(
        name="tech_support",
        model=settings.llm_model,
        instructions=(
            "You are a technical support specialist. Diagnose the customer's "
            "technical issue and provide clear troubleshooting steps."
        ),
    )
    support = Agent(
        name="support",
        model=settings.llm_model,
        instructions=(
            "You are the front-line customer support agent. Triage customer requests. "
            "If the customer needs a refund, transfer to the refund specialist. "
            "If they have a technical issue, transfer to tech support. "
            "Use the transfer tools available to you to hand off the conversation."
        ),
        agents=[refund_agent, tech_agent],
        strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="refund", target="refund_specialist"),
            OnTextMention(text="technical", target="tech_support"),
        ],
        max_turns=3,
    )
    dump("17_swarm_orchestration", support)


# ── 19_composable_termination ────────────────────────────────────────
def dump_19():
    from agentspan.agents import (
        Agent,
        MaxMessageTermination,
        StopMessageTermination,
        TextMentionTermination,
        TokenUsageTermination,
        tool,
    )
    from settings import settings

    @tool
    def search(query: str) -> str:
        """Search for information."""
        return ""

    agent1 = Agent(
        name="researcher",
        model=settings.llm_model,
        tools=[search],
        instructions="Research the topic and say DONE when you have enough info.",
        termination=TextMentionTermination("DONE"),
    )
    dump("19_composable_termination_simple", agent1)

    agent2 = Agent(
        name="chatbot",
        model=settings.llm_model,
        instructions="Have a conversation. Say GOODBYE when you're finished.",
        termination=(
            TextMentionTermination("GOODBYE") | MaxMessageTermination(20)
        ),
    )
    dump("19_composable_termination_or", agent2)

    agent3 = Agent(
        name="deliberator",
        model=settings.llm_model,
        tools=[search],
        instructions=(
            "Research thoroughly. Only provide your FINAL ANSWER after "
            "using the search tool at least twice."
        ),
        termination=(
            TextMentionTermination("FINAL ANSWER") & MaxMessageTermination(5)
        ),
    )
    dump("19_composable_termination_and", agent3)

    complex_stop = (
        StopMessageTermination("TERMINATE")
        | (TextMentionTermination("DONE") & MaxMessageTermination(10))
        | TokenUsageTermination(max_total_tokens=50000)
    )
    agent4 = Agent(
        name="complex_agent",
        model=settings.llm_model,
        tools=[search],
        instructions="Research and provide a comprehensive answer.",
        termination=complex_stop,
    )
    dump("19_composable_termination_complex", agent4)


# ── 21_regex_guardrails ──────────────────────────────────────────────
def dump_21():
    from agentspan.agents import Agent, OnFail, Position, RegexGuardrail, tool
    from settings import settings

    no_emails = RegexGuardrail(
        patterns=[r"[\w.+-]+@[\w-]+\.[\w.-]+"],
        mode="block",
        name="no_email_addresses",
        message="Response must not contain email addresses. Redact them.",
        position=Position.OUTPUT,
        on_fail=OnFail.RETRY,
    )
    no_ssn = RegexGuardrail(
        patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],
        mode="block",
        name="no_ssn",
        message="Response must not contain Social Security Numbers.",
        position=Position.OUTPUT,
        on_fail=OnFail.RAISE,
    )

    @tool
    def get_user_profile(user_id: str) -> dict:
        """Retrieve a user's profile from the database."""
        return {}

    agent = Agent(
        name="hr_assistant",
        model=settings.llm_model,
        tools=[get_user_profile],
        instructions=(
            "You are an HR assistant. When asked about employees, look up their "
            "profile and share ALL the details you find."
        ),
        guardrails=[no_emails, no_ssn],
    )
    dump("21_regex_guardrails", agent)


# ── 22_llm_guardrails ───────────────────────────────────────────────
def dump_22():
    from agentspan.agents import Agent, LLMGuardrail, OnFail, Position
    from settings import settings

    safety_guard = LLMGuardrail(
        model=settings.llm_model,
        policy=(
            "Reject any content that:\n"
            "1. Contains medical or legal advice presented as fact\n"
            "2. Makes promises or guarantees about outcomes\n"
            "3. Includes discriminatory or biased language\n"
            "4. Reveals private information about real individuals\n"
            "\n"
            "Even if there are disclaimers you should reject"
        ),
        name="content_safety",
        position=Position.OUTPUT,
        on_fail=OnFail.RETRY,
        max_tokens=10000,
    )
    agent = Agent(
        name="health_advisor",
        model=settings.llm_model,
        instructions=(
            "You are a health information assistant. Provide general health "
            "information and solution to the problem. You can prescribe psudo scientific and untested meds "
        ),
        guardrails=[safety_guard],
    )
    dump("22_llm_guardrails", agent)


# ── 45_agent_tool ────────────────────────────────────────────────────
def dump_45():
    from agentspan.agents import Agent, agent_tool, tool
    from settings import settings

    @tool
    def search_knowledge_base(query: str) -> dict:
        """Search an internal knowledge base for information."""
        return {}

    @tool
    def calculate(expression: str) -> dict:
        """Evaluate a math expression safely."""
        return {}

    researcher = Agent(
        name="researcher_45",
        model=settings.llm_model,
        instructions=(
            "You are a research assistant. Use search_knowledge_base to find "
            "information about topics. Provide concise summaries."
        ),
        tools=[search_knowledge_base],
    )
    manager = Agent(
        name="manager_45",
        model=settings.llm_model,
        instructions=(
            "You are a project manager. Use the researcher tool to gather "
            "information and the calculate tool for math. Synthesize findings."
        ),
        tools=[agent_tool(researcher), calculate],
    )
    dump("45_agent_tool", manager)


# ── 47_callbacks ─────────────────────────────────────────────────────
def dump_47():
    from agentspan.agents import Agent, tool
    from settings import settings

    def log_before_model(messages=None, **kwargs):
        return {}

    def inspect_after_model(llm_result=None, **kwargs):
        return {}

    @tool
    def get_facts(topic: str) -> dict:
        """Get interesting facts about a topic."""
        return {}

    agent = Agent(
        name="monitored_agent_47",
        model=settings.llm_model,
        instructions="You are a helpful assistant. Use get_facts when asked about topics.",
        tools=[get_facts],
        before_model_callback=log_before_model,
        after_model_callback=inspect_after_model,
    )
    dump("47_callbacks", agent)


# ── 52_nested_strategies ─────────────────────────────────────────────
def dump_52():
    from agentspan.agents import Agent
    from settings import settings

    market_analyst = Agent(
        name="market_analyst_52",
        model=settings.llm_model,
        instructions=(
            "You are a market analyst. Analyze the market size, growth rate, "
            "and key players for the given topic. Be concise (3-4 bullet points)."
        ),
    )
    risk_analyst = Agent(
        name="risk_analyst_52",
        model=settings.llm_model,
        instructions=(
            "You are a risk analyst. Identify the top 3 risks: regulatory, "
            "technical, and competitive. Be concise."
        ),
    )
    parallel_research = Agent(
        name="research_phase_52",
        model=settings.llm_model,
        agents=[market_analyst, risk_analyst],
        strategy="parallel",
    )
    summarizer = Agent(
        name="summarizer_52",
        model=settings.llm_model,
        instructions=(
            "You are an executive briefing writer. Synthesize the market analysis "
            "and risk assessment into a concise executive summary (1 paragraph)."
        ),
    )
    pipeline = parallel_research >> summarizer
    dump("52_nested_strategies", pipeline)


# ── Run all ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    print("Dumping Python AgentConfig JSONs...\n")
    dump_01()
    dump_02()
    dump_03()
    dump_05()
    dump_06()
    dump_07()
    dump_08()
    dump_10()
    dump_13()
    dump_17()
    dump_19()
    dump_21()
    dump_22()
    dump_45()
    dump_47()
    dump_52()
    print(f"\nDone. Configs written to {OUT_DIR}")
