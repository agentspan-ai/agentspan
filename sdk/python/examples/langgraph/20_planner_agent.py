# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Planner Agent — create_agent with plan, execute_step, and review tools.

Demonstrates:
    - A three-stage planning pattern: plan → execute → review, modelled as tools
    - Tools that use LCEL chains with LLM calls inside them
    - The server-side LLM orchestrates the pipeline via tool calls

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import json

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def create_plan(goal: str) -> str:
    """Break a goal into 3-5 concrete, actionable steps.

    Args:
        goal: The high-level goal to decompose into steps.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a project planner. Break the user's goal into 3-5 concrete, "
            "actionable steps. Return ONLY a JSON array of step strings. "
            "Example: [\"Step 1: ...\", \"Step 2: ...\"]"
        )),
        ("human", "Goal: {goal}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"goal": goal})
    raw = response.content.strip()
    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        steps = json.loads(raw.strip())
        if isinstance(steps, list):
            return json.dumps(steps[:5])
    except (json.JSONDecodeError, IndexError):
        pass
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return json.dumps(lines[:5])


@tool
def execute_step(goal: str, step: str) -> str:
    """Execute a single planned step in the context of the overall goal.

    Args:
        goal: The overall goal being pursued.
        step: The specific step to execute.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert executor. Complete the following task step "
            "in the context of the overall goal. Provide a concise result (2-3 sentences)."
        )),
        ("human", "Goal: {goal}\nStep to execute: {step}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"goal": goal, "step": step})
    return f"[{step}]\n{response.content.strip()}"


@tool
def review_results(goal: str, step_results: str) -> str:
    """Review all step results and produce a final consolidated summary.

    Args:
        goal: The overall goal that was pursued.
        step_results: All step execution results joined together.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a quality reviewer. Given the goal and the results of each execution step, "
            "write a concise final review that:\n"
            "1) Confirms whether the goal was achieved\n"
            "2) Highlights the most important outcomes\n"
            "3) Notes any gaps or next actions needed"
        )),
        ("human", "Goal: {goal}\n\nStep Results:\n{step_results}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"goal": goal, "step_results": step_results})
    return response.content


PLANNER_SYSTEM = """You are a project planning and execution agent.

For each goal:
1. Call create_plan to decompose it into 3-5 steps (returns a JSON array)
2. Call execute_step once for EACH step in the plan (use the goal and each step string)
3. Collect all step results and call review_results with the goal and combined results
4. Present the final review to the user

Always complete all steps in the plan before calling review_results.
"""

graph = create_agent(
    llm,
    tools=[create_plan, execute_step, review_results],
    name="planner_agent",
    system_prompt=PLANNER_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Launch a new open-source Python library for data validation.",
        )
        print(f"Status: {result.status}")
        result.print_result()
