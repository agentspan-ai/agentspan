# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent as Tool — using one compiled graph as a tool inside another agent.

Demonstrates:
    - Wrapping a CompiledStateGraph as a LangChain @tool
    - An orchestrator agent calling specialist sub-agents via tool calls
    - Composing complex multi-agent systems from reusable graph components
    - Practical use case: orchestrator dispatching to a math agent and a writing agent

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Specialist agents (as plain compiled graphs) ──────────────────────────────

class SimpleState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _make_specialist(system_prompt: str) -> object:
    specialist_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    def node(state: SimpleState) -> SimpleState:
        msgs = [SystemMessage(content=system_prompt)] + state["messages"]
        response = specialist_llm.invoke(msgs)
        return {"messages": [response]}

    b = StateGraph(SimpleState)
    b.add_node("specialist", node)
    b.add_edge(START, "specialist")
    b.add_edge("specialist", END)
    return b.compile()


math_graph = _make_specialist(
    "You are a math expert. Solve mathematical problems precisely with step-by-step reasoning."
)

writing_graph = _make_specialist(
    "You are a professional writer and editor. Help craft, improve, and polish written content."
)

trivia_graph = _make_specialist(
    "You are a trivia expert. Answer questions about history, science, culture, and general knowledge."
)


# ── Wrap specialist graphs as @tool callables ─────────────────────────────────

@tool
def ask_math_expert(question: str) -> str:
    """Send a math problem to the math specialist agent and get the answer."""
    result = math_graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content


@tool
def ask_writing_expert(task: str) -> str:
    """Send a writing task to the writing specialist agent and get the result."""
    result = writing_graph.invoke({"messages": [HumanMessage(content=task)]})
    return result["messages"][-1].content


@tool
def ask_trivia_expert(question: str) -> str:
    """Look up a trivia fact or answer a general knowledge question."""
    result = trivia_graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content


# ── Orchestrator agent ────────────────────────────────────────────────────────

tools = [ask_math_expert, ask_writing_expert, ask_trivia_expert]
orchestrator_llm = llm.bind_tools(tools)


def orchestrator(state: SimpleState) -> SimpleState:
    system = SystemMessage(
        content=(
            "You are an orchestrator. Route tasks to the appropriate specialist:\n"
            "- Math problems → ask_math_expert\n"
            "- Writing/editing tasks → ask_writing_expert\n"
            "- General knowledge/trivia → ask_trivia_expert\n"
            "Combine the specialist's answer into a final helpful response."
        )
    )
    msgs = [system] + state["messages"]
    response = orchestrator_llm.invoke(msgs)
    return {"messages": [response]}


tool_node = ToolNode(tools)

orch_builder = StateGraph(SimpleState)
orch_builder.add_node("orchestrator", orchestrator)
orch_builder.add_node("tools", tool_node)
orch_builder.add_edge(START, "orchestrator")
orch_builder.add_conditional_edges("orchestrator", tools_condition)
orch_builder.add_edge("tools", "orchestrator")

graph = orch_builder.compile(name="orchestrator_with_subagents")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            result.print_result()
            print("-" * 60)

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.40_agent_as_tool
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
