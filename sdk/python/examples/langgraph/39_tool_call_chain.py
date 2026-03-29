# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool Call Chain — chaining multiple tool calls in sequence.

Demonstrates:
    - An agent that must call several tools in a defined order
    - Using ToolNode and tools_condition for standard LangGraph tool loop
    - State accumulation across multiple tool invocations
    - Practical use case: data enrichment pipeline (fetch → transform → validate → summarize)

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import TypedDict, Annotated
import operator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Tools ─────────────────────────────────────────────────────────────────────

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


# ── Agent ─────────────────────────────────────────────────────────────────────

tools = [fetch_company_info, calculate_company_age, get_sector_peers, generate_investment_note]
llm_with_tools = llm.bind_tools(tools)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def agent(state: State) -> State:
    system = SystemMessage(
        content=(
            "You are a financial analyst. For each company query, you MUST:\n"
            "1. Fetch company info\n"
            "2. Calculate company age using the founded year\n"
            "3. Get sector peers\n"
            "4. Generate an investment note combining all facts\n"
            "Call the tools in this order."
        )
    )
    messages = [system] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(tools)

builder = StateGraph(State)
builder.add_node("agent", agent)
builder.add_node("tools", tool_node)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile(name="tool_call_chain_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.39_tool_call_chain
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(graph, "Analyze Anthropic for investment purposes.")
        # print(f"Status: {result.status}")
        # result.print_result()
