# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Reflection Agent — self-critique and iterative improvement.

Demonstrates:
    - A generate → reflect → improve loop
    - Stopping when the critic judges the output acceptable or after max rounds
    - How to track iteration count in state
    - Practical use case: essay generation with quality self-improvement

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

MAX_ITERATIONS = 3


class State(TypedDict):
    topic: str
    draft: str
    critique: str
    iterations: int
    final_output: str


def generate(state: State) -> State:
    """Generate or improve an essay based on previous critique."""
    iterations = state.get("iterations", 0)
    if iterations == 0:
        prompt = f"Write a concise, well-structured paragraph about: {state['topic']}"
    else:
        prompt = (
            f"Improve this paragraph about '{state['topic']}' based on the critique below.\n\n"
            f"Current draft:\n{state['draft']}\n\n"
            f"Critique:\n{state['critique']}\n\n"
            "Return only the improved paragraph."
        )
    response = llm.invoke([
        SystemMessage(content="You are a skilled writer. Produce clear, engaging prose."),
        HumanMessage(content=prompt),
    ])
    return {"draft": response.content.strip(), "iterations": iterations + 1}


def reflect(state: State) -> State:
    """Critique the current draft for quality."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a rigorous editor. Critique the paragraph on:\n"
                "1. Clarity\n2. Accuracy\n3. Engagement\n4. Conciseness\n\n"
                "If the paragraph is already excellent, start your response with 'APPROVE'. "
                "Otherwise start with 'REVISE' and list specific improvements."
            )
        ),
        HumanMessage(content=f"Topic: {state['topic']}\n\nParagraph:\n{state['draft']}"),
    ])
    return {"critique": response.content.strip()}


def should_continue(state: State) -> str:
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        return "done"
    critique = state.get("critique", "")
    if critique.upper().startswith("APPROVE"):
        return "done"
    return "improve"


def finalize(state: State) -> State:
    return {"final_output": state["draft"]}


builder = StateGraph(State)
builder.add_node("generate", generate)
builder.add_node("reflect", reflect)
builder.add_node("finalize", finalize)

builder.add_edge(START, "generate")
builder.add_edge("generate", "reflect")
builder.add_conditional_edges(
    "reflect",
    should_continue,
    {"improve": "generate", "done": "finalize"},
)
builder.add_edge("finalize", END)

graph = builder.compile(name="reflection_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.32_reflection_agent
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "the importance of open-source software in modern technology",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
