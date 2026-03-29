# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Planner Agent — StateGraph with plan → execute_steps → review pipeline.

Demonstrates:
    - A three-stage planning agent: LLM creates a plan, executes each step, then reviews
    - Iterating over dynamically generated plan steps in the state
    - Using TypedDict with a list of steps and accumulated results
    - Practical use case: project breakdown and task execution

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json
from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class State(TypedDict):
    goal: str
    steps: List[str]
    step_results: List[str]
    review: str


def plan(state: State) -> State:
    """Use the LLM to decompose the goal into 3-5 concrete, actionable steps."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a project planner. Break the user's goal into 3-5 concrete, "
                "actionable steps. Return ONLY a JSON array of step strings. "
                "Example: [\"Step 1: ...\", \"Step 2: ...\"]"
            )
        ),
        HumanMessage(content=f"Goal: {state['goal']}"),
    ])

    raw = response.content.strip()
    # Extract JSON array from the response
    try:
        # Handle markdown code blocks
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        steps = json.loads(raw.strip())
        if not isinstance(steps, list):
            steps = [raw]
    except (json.JSONDecodeError, IndexError):
        # Fallback: split by newlines
        steps = [line.strip() for line in raw.split("\n") if line.strip()]

    return {"steps": steps[:5], "step_results": []}


def execute_steps(state: State) -> State:
    """Execute each planned step and collect the results."""
    results = list(state.get("step_results", []))

    for step in state["steps"]:
        response = llm.invoke([
            SystemMessage(
                content=(
                    "You are an expert executor. Complete the following task step "
                    "in the context of the overall goal. Provide a concise result (2-3 sentences)."
                )
            ),
            HumanMessage(content=f"Goal: {state['goal']}\nStep to execute: {step}"),
        ])
        results.append(f"[{step}]\n{response.content.strip()}")

    return {"step_results": results}


def review(state: State) -> State:
    """Review all step results and produce a final consolidated summary."""
    steps_summary = "\n\n".join(state["step_results"])
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a quality reviewer. Given the goal and the results of each execution step, "
                "write a concise final review that:\n"
                "1) Confirms whether the goal was achieved\n"
                "2) Highlights the most important outcomes\n"
                "3) Notes any gaps or next actions needed"
            )
        ),
        HumanMessage(
            content=(
                f"Goal: {state['goal']}\n\n"
                f"Step Results:\n{steps_summary}"
            )
        ),
    ])
    return {"review": response.content}


builder = StateGraph(State)
builder.add_node("plan", plan)
builder.add_node("execute", execute_steps)
builder.add_node("review", review)

builder.add_edge(START, "plan")
builder.add_edge("plan", "execute")
builder.add_edge("execute", "review")
builder.add_edge("review", END)

graph = builder.compile(name="planner_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.20_planner_agent
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "Launch a new open-source Python library for data validation.",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
