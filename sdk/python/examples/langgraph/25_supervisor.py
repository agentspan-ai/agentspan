# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Supervisor — multi-agent supervisor pattern.

Demonstrates:
    - A supervisor LLM that decides which specialist agent to call next
    - Routing control flow based on the supervisor's decision
    - Collecting outputs from specialized sub-agents
    - Practical use case: research → writing → editing pipeline with supervisor control

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

AGENTS = ["researcher", "writer", "editor"]


class State(TypedDict):
    task: str
    research: str
    draft: str
    final_article: str
    next_agent: str
    completed: List[str]


def supervisor(state: State) -> State:
    """Decide which agent to call next based on what has been done."""
    completed = state.get("completed", [])
    if "researcher" not in completed:
        return {"next_agent": "researcher"}
    if "writer" not in completed:
        return {"next_agent": "writer"}
    if "editor" not in completed:
        return {"next_agent": "editor"}
    return {"next_agent": "FINISH"}


def researcher(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a researcher. Gather key facts and insights about the topic in 3-5 bullet points."),
        HumanMessage(content=f"Topic: {state['task']}"),
    ])
    completed = list(state.get("completed", []))
    completed.append("researcher")
    return {"research": response.content.strip(), "completed": completed}


def writer(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are a writer. Using the research notes, write a short article (3 paragraphs)."),
        HumanMessage(content=f"Topic: {state['task']}\n\nResearch:\n{state['research']}"),
    ])
    completed = list(state.get("completed", []))
    completed.append("writer")
    return {"draft": response.content.strip(), "completed": completed}


def editor(state: State) -> State:
    response = llm.invoke([
        SystemMessage(content="You are an editor. Improve clarity, flow, and correctness of the article. Return the polished version only."),
        HumanMessage(content=state["draft"]),
    ])
    completed = list(state.get("completed", []))
    completed.append("editor")
    return {"final_article": response.content.strip(), "completed": completed}


def route(state: State) -> str:
    return state.get("next_agent", "FINISH")


builder = StateGraph(State)
builder.add_node("supervisor", supervisor)
builder.add_node("researcher", researcher)
builder.add_node("writer", writer)
builder.add_node("editor", editor)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges(
    "supervisor",
    route,
    {"researcher": "researcher", "writer": "writer", "editor": "editor", "FINISH": END},
)
builder.add_edge("researcher", "supervisor")
builder.add_edge("writer", "supervisor")
builder.add_edge("editor", "supervisor")

graph = builder.compile(name="supervisor_multiagent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "The impact of large language models on software development")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.25_supervisor
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
