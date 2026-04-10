# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Advanced Orchestration — complex multi-tool agent with planning and synthesis.

Demonstrates:
    - Multi-domain tool set with prioritization
    - Task decomposition via a planning tool
    - Synthesizing results from multiple tool calls into a coherent report

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from datetime import datetime

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def get_company_info(company: str) -> str:
    """Retrieve company profile information.

    Args:
        company: The company name or ticker symbol.
    """
    companies = {
        "openai": {"name": "OpenAI", "founded": 2015, "ceo": "Sam Altman", "focus": "AGI research and deployment", "valuation": "$157B (2025)"},
        "anthropic": {"name": "Anthropic", "founded": 2021, "ceo": "Dario Amodei", "focus": "AI safety research", "valuation": "$61B (2025)"},
        "google": {"name": "Alphabet/Google", "founded": 1998, "ceo": "Sundar Pichai", "focus": "Search, cloud, AI", "valuation": "$2.1T (2025)"},
        "microsoft": {"name": "Microsoft", "founded": 1975, "ceo": "Satya Nadella", "focus": "Cloud, AI, productivity", "valuation": "$3.1T (2025)"},
    }
    key = company.lower().replace(".", "").replace(",", "")
    for k, v in companies.items():
        if k in key or key in k:
            return json.dumps(v, indent=2)
    return f"No company profile found for '{company}'."


@tool
def get_market_trends(sector: str) -> str:
    """Retrieve current market trends for a sector.

    Args:
        sector: The industry sector (e.g., 'AI', 'cloud computing', 'fintech').
    """
    trends = {
        "ai": "Key trends: LLM commoditization, multimodal AI, agentic systems, edge AI deployment. Growth: 37% CAGR through 2030.",
        "cloud computing": "Key trends: hybrid cloud, serverless, FinOps cost optimization, AI/ML infrastructure. Market: $670B by 2025.",
        "fintech": "Key trends: embedded finance, BNPL regulation, CBDCs, AI fraud detection. Investment: $50B in 2024.",
        "cybersecurity": "Key trends: zero-trust architecture, AI-driven threat detection, ransomware surge. Market: $300B by 2026.",
        "healthcare": "Key trends: AI diagnostics, telemedicine growth, personalized medicine, EHR integration. Market: $500B by 2026.",
    }
    for key, trend in trends.items():
        if key in sector.lower():
            return trend
    return f"No trend data for sector '{sector}'."


@tool
def calculate_metric(formula: str, values: str) -> str:
    """Compute a business metric using a named formula and input values.

    Args:
        formula: The metric name (e.g., 'ROI', 'CAGR', 'market_share').
        values: JSON string with the required input values.
    """
    try:
        data = json.loads(values)
    except json.JSONDecodeError:
        return "Error: values must be a valid JSON string."

    formula_lower = formula.lower()
    try:
        if "roi" in formula_lower:
            gain = float(data.get("gain", 0))
            cost = float(data.get("cost", 1))
            roi = ((gain - cost) / cost) * 100
            return f"ROI = {roi:.1f}%"
        if "cagr" in formula_lower:
            start = float(data.get("start", 1))
            end = float(data.get("end", 1))
            years = float(data.get("years", 1))
            cagr = ((end / start) ** (1 / years) - 1) * 100
            return f"CAGR = {cagr:.1f}%"
        if "market_share" in formula_lower:
            company = float(data.get("company", 0))
            total = float(data.get("total", 1))
            share = (company / total) * 100
            return f"Market share = {share:.1f}%"
        return f"Unknown formula '{formula}'. Supported: ROI, CAGR, market_share."
    except (TypeError, ZeroDivisionError) as e:
        return f"Calculation error: {e}"


@tool
def generate_report_section(section_type: str, content: str) -> str:
    """Format content as a professional report section.

    Args:
        section_type: Type of section ('executive_summary', 'findings', 'recommendations').
        content: The raw content to format.
    """
    now = datetime.now().strftime("%Y-%m-%d")
    templates = {
        "executive_summary": f"## Executive Summary\n*Report Date: {now}*\n\n{content}",
        "findings": f"## Key Findings\n\n{content}",
        "recommendations": f"## Recommendations\n\n{content}",
    }
    key = section_type.lower().replace(" ", "_")
    return templates.get(key, f"## {section_type.title()}\n\n{content}")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_company_info, get_market_trends, calculate_metric, generate_report_section]

graph = create_agent(
    llm,
    tools=tools,
    name="advanced_orchestration_agent",
    system_prompt=(
        "You are a senior business intelligence analyst. When given a research request, "
        "systematically gather company data, market trends, and compute relevant metrics. "
        "Then synthesize everything into a structured report with findings and recommendations."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Produce a brief competitive analysis of OpenAI and Anthropic. "
            "Include AI market trends and calculate the CAGR if the AI market grows from $200B in 2024 to $1.8T by 2030.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.25_advanced_orchestration
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
