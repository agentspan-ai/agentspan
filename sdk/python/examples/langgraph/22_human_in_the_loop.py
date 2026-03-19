# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-Loop — draft, review, and revise email with agent tools.

Demonstrates:
    - An agent that drafts an email, then incorporates human feedback via a tool call
    - Human approval is modelled as an input parameter to the revise_email tool
    - Practical use case: draft an email, wait for human approval, then send

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def draft_email(request: str) -> str:
    """Draft a concise, professional email based on the request.

    Args:
        request: Description of the email to draft (purpose, recipient, key points).
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a professional email writer. Draft a concise, polite email."),
        ("human", "Request: {request}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"request": request})
    return f"[DRAFT EMAIL]\n{response.content.strip()}"


@tool
def revise_email(draft: str, feedback: str) -> str:
    """Revise an email draft based on human feedback.

    If feedback is 'approve', 'ok', or 'looks good', return the draft as-is.
    Otherwise apply the feedback and return the revised version.

    Args:
        draft: The original email draft.
        feedback: Human reviewer's feedback or 'approve' to accept as-is.
    """
    if feedback.lower() in ("approve", "ok", "looks good", "approved"):
        return f"[FINAL EMAIL — APPROVED]\n{draft}"

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Revise the email draft based on the feedback provided."),
        ("human", "Original draft:\n{draft}\n\nFeedback:\n{feedback}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"draft": draft, "feedback": feedback})
    return f"[REVISED EMAIL]\n{response.content.strip()}"


HITL_SYSTEM = """You are an email writing assistant with human-in-the-loop review.

When asked to write an email:
1. Call draft_email to create the initial draft
2. Present the draft to the user and ask for their feedback
3. If feedback is provided (or if the user approves), call revise_email with the draft and feedback
4. Return the final version

If the user just says 'approve' or similar, pass that directly to revise_email.
"""

graph = create_agent(
    llm,
    tools=[draft_email, revise_email],
    name="email_hitl_agent",
    system_prompt=HITL_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Turn 1: Draft the email
        print("=== Turn 1: drafting email ===")
        result = runtime.run(
            graph,
            "Draft an email to schedule a team meeting for next Monday at 10am to discuss Q3 plans.",
            session_id="email-session-1",
        )
        result.print_result()

        # Turn 2: Approve
        print("\n=== Turn 2: human approves ===")
        result = runtime.run(
            graph,
            "approve",
            session_id="email-session-1",
        )
        result.print_result()
