# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Debate Agents — two agents arguing opposing positions.

Demonstrates:
    - Two specialized agents with opposing system prompts
    - Alternating turns tracked in state
    - A judge agent that evaluates the debate and declares a winner
    - Practical use case: pros/cons analysis, brainstorming, red-teaming

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

MAX_ROUNDS = 2


class Turn(TypedDict):
    speaker: str
    argument: str


class State(TypedDict):
    topic: str
    turns: List[Turn]
    round: int
    verdict: str


def agent_pro(state: State) -> State:
    """Argues in favour of the topic."""
    previous = "\n".join(
        f"{t['speaker']}: {t['argument']}" for t in state.get("turns", [])
    )
    prompt = f"Topic: {state['topic']}"
    if previous:
        prompt += f"\n\nDebate so far:\n{previous}\n\nNow make your argument in favour (2-3 sentences)."
    else:
        prompt += "\n\nMake your opening argument in favour of this topic (2-3 sentences)."

    response = llm.invoke([
        SystemMessage(content="You are a persuasive debater arguing IN FAVOUR of the given topic. Be concise and compelling."),
        HumanMessage(content=prompt),
    ])
    turns = list(state.get("turns", []))
    turns.append({"speaker": "PRO", "argument": response.content.strip()})
    return {"turns": turns}


def agent_con(state: State) -> State:
    """Argues against the topic."""
    previous = "\n".join(
        f"{t['speaker']}: {t['argument']}" for t in state.get("turns", [])
    )
    response = llm.invoke([
        SystemMessage(content="You are a persuasive debater arguing AGAINST the given topic. Be concise and direct."),
        HumanMessage(
            content=f"Topic: {state['topic']}\n\nDebate so far:\n{previous}\n\nMake your counter-argument (2-3 sentences)."
        ),
    ])
    turns = list(state.get("turns", []))
    turns.append({"speaker": "CON", "argument": response.content.strip()})
    return {"turns": turns, "round": state.get("round", 0) + 1}


def judge(state: State) -> State:
    """Evaluate the debate and declare a winner with reasoning."""
    transcript = "\n\n".join(
        f"{t['speaker']}: {t['argument']}" for t in state.get("turns", [])
    )
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are an impartial debate judge. Review the debate transcript and:\n"
                "1. Identify which side made the stronger arguments\n"
                "2. Declare the winner (PRO or CON) and explain why in 2-3 sentences\n"
                "3. Note any logical fallacies or weak points"
            )
        ),
        HumanMessage(content=f"Debate topic: {state['topic']}\n\nTranscript:\n{transcript}"),
    ])
    return {"verdict": response.content.strip()}


def continue_or_judge(state: State) -> str:
    if state.get("round", 0) >= MAX_ROUNDS:
        return "judge"
    return "con"


builder = StateGraph(State)
builder.add_node("pro", agent_pro)
builder.add_node("con", agent_con)
builder.add_node("judge", judge)

builder.add_edge(START, "pro")
builder.add_conditional_edges("con", continue_or_judge, {"judge": "judge", "con": "pro"})
builder.add_edge("pro", "con")
builder.add_edge("judge", END)

graph = builder.compile(name="debate_agents")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.36_debate_agents
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "Artificial intelligence will create more jobs than it destroys.",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
