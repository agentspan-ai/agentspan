# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Advanced Orchestration — LangGraph agent orchestrating a multi-step pipeline.

Demonstrates:
    - Tools that themselves invoke LLM chains (nested LLM calls)
    - A pipeline agent that decomposes tasks, assigns subtasks, and aggregates results
    - Combining structured output, prompt templates, and output parsers
    - Practical use case: automated business report generation from raw data inputs

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List
from pydantic import BaseModel, Field

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
str_parser = StrOutputParser()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReportSection(BaseModel):
    title: str = Field(description="Section title")
    content: str = Field(description="Section content")
    key_metrics: List[str] = Field(description="List of key metrics or data points")


class ExecutiveReport(BaseModel):
    report_title: str = Field(description="Title of the report")
    executive_summary: str = Field(description="2-3 sentence executive summary")
    sections: List[ReportSection] = Field(description="Report sections")
    recommendations: List[str] = Field(description="3-5 actionable recommendations")
    risk_factors: List[str] = Field(description="Key risks to be aware of")


report_parser = JsonOutputParser(pydantic_object=ExecutiveReport)


# ── Chain-based tools ─────────────────────────────────────────────────────────

@tool
def analyze_market_data(company: str, sector: str) -> str:
    """Analyze market position and competitive landscape for a company.

    Args:
        company: Company name.
        sector: Industry sector.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a market analyst. Provide a concise market analysis in 3-4 sentences covering position, trends, and competition."),
        ("human", "Analyze the market position of {company} in the {sector} sector."),
    ])
    chain = prompt | llm | str_parser
    return chain.invoke({"company": company, "sector": sector})


@tool
def generate_financial_metrics(company: str, revenue: str, growth_rate: str) -> str:
    """Calculate and interpret key financial metrics.

    Args:
        company: Company name.
        revenue: Annual revenue (e.g., '$5M', '$120M').
        growth_rate: YoY growth rate (e.g., '25%', '-5%').
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a financial analyst. Interpret these metrics and derive key insights including valuation implications."),
        ("human", "Company: {company}\nRevenue: {revenue}\nGrowth: {growth_rate}\n\nProvide 4-5 key financial insights."),
    ])
    chain = prompt | llm | str_parser
    return chain.invoke({"company": company, "revenue": revenue, "growth_rate": growth_rate})


@tool
def assess_risks(company: str, sector: str, growth_rate: str) -> str:
    """Assess key business risks for a company.

    Args:
        company: Company name.
        sector: Industry sector.
        growth_rate: Current growth rate.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a risk analyst. Identify the top 4-5 specific risks for this company, considering sector dynamics and growth trajectory."),
        ("human", "{company} in {sector} growing at {growth_rate}"),
    ])
    chain = prompt | llm | str_parser
    return chain.invoke({"company": company, "sector": sector, "growth_rate": growth_rate})


@tool
def compile_report(
    company: str,
    market_analysis: str,
    financial_metrics: str,
    risk_assessment: str,
) -> str:
    """Compile all findings into a structured executive report.

    Args:
        company: Company name.
        market_analysis: Market analysis text.
        financial_metrics: Financial metrics text.
        risk_assessment: Risk assessment text.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are a business consultant creating an executive report. {report_parser.get_format_instructions()}"),
        ("human", (
            "Create an executive report for {company}.\n\n"
            "Market Analysis:\n{market_analysis}\n\n"
            "Financial Metrics:\n{financial_metrics}\n\n"
            "Risk Assessment:\n{risk_assessment}"
        )),
    ])
    chain = prompt | llm | report_parser
    try:
        report = chain.invoke({
            "company": company,
            "market_analysis": market_analysis,
            "financial_metrics": financial_metrics,
            "risk_assessment": risk_assessment,
        })
        if isinstance(report, dict):
            sections_text = ""
            for sec in report.get("sections", []):
                metrics = "\n".join(f"  • {m}" for m in sec.get("key_metrics", []))
                sections_text += f"\n{sec['title']}:\n{sec['content']}\n{metrics}\n"

            recs = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(report.get("recommendations", [])))
            risks = "\n".join(f"  ! {r}" for r in report.get("risk_factors", []))

            return (
                f"{'='*60}\n"
                f"{report.get('report_title', 'Executive Report')}\n"
                f"{'='*60}\n\n"
                f"EXECUTIVE SUMMARY:\n{report.get('executive_summary', '')}\n"
                f"{sections_text}\n"
                f"RECOMMENDATIONS:\n{recs}\n\n"
                f"KEY RISKS:\n{risks}\n"
            )
        return str(report)
    except Exception as e:
        return f"Report compilation error: {e}"


ORCHESTRATOR_SYSTEM = """You are a senior business intelligence orchestrator.
For each company analysis request:
1. Analyze the market data first
2. Calculate and interpret financial metrics
3. Assess key business risks
4. Compile everything into a structured executive report
Always call all four tools and combine their outputs in the final report.
"""

graph = create_react_agent(
    llm,
    tools=[analyze_market_data, generate_financial_metrics, assess_risks, compile_report],
    prompt=ORCHESTRATOR_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.45_advanced_orchestration
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "Generate a complete executive report for TechStartup Inc., "
        # "a SaaS company in the cloud infrastructure sector with $12M annual revenue "
        # "and 45% year-over-year growth.",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
