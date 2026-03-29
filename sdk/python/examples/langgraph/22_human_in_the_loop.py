# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop — real human approval gate within a LangGraph workflow.

Demonstrates:
    - Draft → Human Review → Approve/Revise conditional workflow
    - A Conductor HUMAN task that pauses execution for actual human input
    - The human provides a verdict (APPROVE/REVISE) and feedback
    - Conditional routing based on human verdict
    - LLM nodes compiled as server-side LLM_CHAT_COMPLETE tasks
    - Running the full workflow through Agentspan via runtime.run()

The workflow pauses at the review step and waits for a human to approve or
reject the draft via the AgentSpan UI or API. This is true human-in-the-loop,
not an LLM simulating a reviewer.

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agentspan.agents import AgentRuntime
from agentspan.agents.frameworks.langgraph import human_task

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


class EmailState(TypedDict):
    request: str
    draft: str
    review_verdict: str
    review_feedback: str
    final_email: str


def draft_email(state: EmailState) -> EmailState:
    """Generate an email draft from the request."""
    response = llm.invoke([
        SystemMessage(
            content="You are a professional email writer. Draft a concise, polite email. "
            "Include a subject line, greeting, body, and sign-off."
        ),
        HumanMessage(content=f"Request: {state['request']}"),
    ])
    return {"draft": response.content.strip()}


@human_task(prompt="Review the email draft. Respond with review_verdict (APPROVE or REVISE) and review_feedback.")
def review_email(state: EmailState) -> EmailState:
    """Human reviews the email draft and provides verdict + feedback.

    This node compiles to a Conductor HUMAN task that pauses execution.
    The human sees the current state (including the draft) and responds
    with review_verdict and review_feedback fields.
    """
    pass


def route_after_review(state: EmailState) -> str:
    """Route based on human reviewer verdict."""
    if state.get("review_verdict", "").upper() == "APPROVE":
        return "finalize"
    return "revise"


def finalize(state: EmailState) -> EmailState:
    """Approve the draft as the final email."""
    return {"final_email": state["draft"]}


def revise_email(state: EmailState) -> EmailState:
    """Revise a rejected draft using the human's feedback."""
    response = llm.invoke([
        SystemMessage(
            content="You are a professional email writer. Revise this email draft "
            "to address the reviewer's feedback. Keep the same intent but improve quality."
        ),
        HumanMessage(
            content=f"Original request: {state.get('request', '')}\n\n"
            f"Current draft:\n{state['draft']}\n\n"
            f"Reviewer feedback: {state.get('review_feedback', 'Needs improvement.')}"
        ),
    ])
    return {"final_email": response.content.strip()}


builder = StateGraph(EmailState)
builder.add_node("draft", draft_email)
builder.add_node("review", review_email)
builder.add_node("finalize", finalize)
builder.add_node("revise", revise_email)

builder.add_edge(START, "draft")
builder.add_edge("draft", "review")
builder.add_conditional_edges(
    "review", route_after_review, {"finalize": "finalize", "revise": "revise"}
)
builder.add_edge("finalize", END)
builder.add_edge("revise", END)

graph = builder.compile(name="email_hitl_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.22_human_in_the_loop
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph, "Schedule a team meeting for next Monday at 10am to discuss Q3 plans."
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
