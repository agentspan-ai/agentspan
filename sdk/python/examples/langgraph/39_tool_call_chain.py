# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Call Chain — chaining multiple tool calls in sequence.

Demonstrates:
    - An agent that calls several tools in a defined order
    - create_agent handles the ReAct loop automatically (no manual ToolNode/tools_condition)
    - State accumulation across multiple tool invocations
    - Practical use case: data enrichment pipeline (fetch → transform → validate → summarize)

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def fetch_company_info(company_name: str) -> str:
    """Look up basic information about a company."""
    data = {
        "openai": {"founded": 2015, "employees": "~1500", "sector": "AI Research"},
        "google": {"founded": 1998, "employees": "~190000", "sector": "Technology"},
        "microsoft": {"founded": 1975, "employees": "~220000", "sector": "Technology"},
        "anthropic": {"founded": 2021, "employees": "~500", "sector": "AI Safety"},
    }
    key = company_name.lower()
    if key in data:
        return json.dumps(data[key])
    return json.dumps({"error": f"Company '{company_name}' not found in database"})


@tool
def calculate_company_age(founded_year: int) -> str:
    """Calculate how many years a company has been in operation."""
    current_year = 2025
    age = current_year - founded_year
    return f"The company has been operating for {age} years (founded {founded_year})"


@tool
def get_sector_peers(sector: str) -> str:
    """Return a list of well-known companies in the same sector."""
    peers = {
        "ai research": ["OpenAI", "Anthropic", "DeepMind", "Cohere"],
        "ai safety": ["Anthropic", "OpenAI", "Redwood Research"],
        "technology": ["Apple", "Microsoft", "Google", "Meta", "Amazon"],
    }
    key = sector.lower()
    if key in peers:
        return f"Peers in '{sector}': {', '.join(peers[key])}"
    return f"No peer data available for sector: {sector}"


@tool
def generate_investment_note(company: str, age: str, peers: str) -> str:
    """Generate a brief investment note combining company facts."""
    return (
        f"Investment Note — {company}\n"
        f"Operational history: {age}\n"
        f"Competitive landscape: {peers}\n"
        f"Recommendation: Review financials and recent growth metrics before investing."
    )


graph = create_agent(
    llm,
    tools=[fetch_company_info, calculate_company_age, get_sector_peers, generate_investment_note],
    system_prompt=(
        "You are a financial analyst. For each company query, you MUST:\n"
        "1. Fetch company info\n"
        "2. Calculate company age using the founded year\n"
        "3. Get sector peers\n"
        "4. Generate an investment note combining all facts\n"
        "Call the tools in this order."
    ),
    name="tool_call_chain_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Analyze Anthropic for investment purposes.")
        print(f"Status: {result.status}")
        result.print_result()
