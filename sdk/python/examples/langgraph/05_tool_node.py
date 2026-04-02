# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""ToolNode — StateGraph with ToolNode + tools_condition for ReAct loop.

Demonstrates:
    - Manually building a ReAct loop with StateGraph
    - Using ToolNode to execute tool calls returned by the LLM
    - Using tools_condition to route between tool execution and END
    - Annotated list reducer for message accumulation

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from agentspan.agents import AgentRuntime


@tool
def lookup_capital(country: str) -> str:
    """Look up the capital city of a country."""
    capitals = {
        "france": "Paris",
        "germany": "Berlin",
        "japan": "Tokyo",
        "brazil": "Brasília",
        "australia": "Canberra",
        "india": "New Delhi",
        "usa": "Washington D.C.",
        "canada": "Ottawa",
    }
    return capitals.get(country.lower(), f"Capital of {country} is not in my database.")


@tool
def lookup_population(country: str) -> str:
    """Return the approximate population of a country (in millions)."""
    populations = {
        "france": "68 million",
        "germany": "84 million",
        "japan": "125 million",
        "brazil": "215 million",
        "australia": "26 million",
        "india": "1.4 billion",
        "usa": "335 million",
        "canada": "38 million",
    }
    return populations.get(country.lower(), f"Population data for {country} is not available.")


tools = [lookup_capital, lookup_population]
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_with_tools = llm.bind_tools(tools)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


def call_model(state: State) -> State:
    """Call the LLM; it may emit tool calls or a final answer."""
    system = SystemMessage(content="You are a helpful geography assistant. Use tools to look up facts.")
    response = llm_with_tools.invoke([system] + state["messages"])
    return {"messages": [response]}


tool_node = ToolNode(tools)

builder = StateGraph(State)
builder.add_node("agent", call_model)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile(name="tool_node_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "What is the capital and population of Japan and Brazil?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.05_tool_node
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
