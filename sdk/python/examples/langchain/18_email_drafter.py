# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Email Drafter — AI-powered professional email writing assistant.

Demonstrates:
    - Generating professional emails for various scenarios
    - Subject line optimization
    - Follow-up and reply drafting
    - Tone adjustment (formal, friendly, assertive)
    - Practical use case: business communication assistant

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)


@tool
def draft_email(
    purpose: str,
    recipient_name: str,
    sender_name: str,
    key_points: str,
    tone: str = "professional",
) -> str:
    """Draft a complete professional email.

    Args:
        purpose: The goal of the email (e.g., 'meeting request', 'follow-up', 'apology').
        recipient_name: Name of the email recipient.
        sender_name: Name of the email sender.
        key_points: Comma-separated list of key points to include.
        tone: Email tone — 'formal', 'professional', 'friendly', 'assertive'.
    """
    response = llm.invoke(
        f"Write a complete {tone} email.\n"
        f"Purpose: {purpose}\n"
        f"From: {sender_name}\n"
        f"To: {recipient_name}\n"
        f"Key points to include: {key_points}\n\n"
        f"Include: Subject line, greeting, body paragraphs, closing, signature.\n"
        f"Format the subject line as 'Subject: [subject text]' on the first line."
    )
    return response.content.strip()


@tool
def write_follow_up(
    original_email_summary: str,
    days_since_sent: int,
    your_name: str,
    recipient_name: str,
) -> str:
    """Write a follow-up email when you haven't received a response.

    Args:
        original_email_summary: Brief summary of what the original email was about.
        days_since_sent: How many days have passed since the original email.
        your_name: Your name for the signature.
        recipient_name: Recipient's name for the greeting.
    """
    urgency = "gentle" if days_since_sent < 5 else "polite but firm"
    response = llm.invoke(
        f"Write a {urgency} follow-up email.\n"
        f"Original email was about: {original_email_summary}\n"
        f"Sent {days_since_sent} days ago with no response.\n"
        f"From: {your_name} | To: {recipient_name}\n"
        f"Keep it concise (3-4 sentences), acknowledge they may be busy, restate the ask."
    )
    return f"[FOLLOW-UP EMAIL]\n{response.content.strip()}"


@tool
def write_reply(
    original_message: str,
    your_response: str,
    your_name: str,
    tone: str = "professional",
) -> str:
    """Draft a reply to an incoming email.

    Args:
        original_message: The email you received that you need to reply to.
        your_response: Your intended response/answer in plain language.
        your_name: Your name for the signature.
        tone: Reply tone — 'professional', 'friendly', 'formal'.
    """
    response = llm.invoke(
        f"Write a {tone} email reply.\n"
        f"Original message:\n{original_message}\n\n"
        f"My intended response: {your_response}\n"
        f"Signed by: {your_name}\n\n"
        f"Make the reply polished and complete."
    )
    return f"[REPLY]\n{response.content.strip()}"


@tool
def improve_email(draft: str, improvements: str) -> str:
    """Improve an existing email draft based on specific feedback.

    Args:
        draft: The existing email draft to improve.
        improvements: Specific improvements to make (e.g., 'make it shorter', 'be more assertive').
    """
    response = llm.invoke(
        f"Improve this email based on the following instructions:\n"
        f"Instructions: {improvements}\n\n"
        f"Original email:\n{draft}\n\n"
        f"Return the improved version only."
    )
    return f"[IMPROVED VERSION]\n{response.content.strip()}"


EMAIL_SYSTEM = """You are a professional business communication assistant.
When helping with emails:
- Always use clear, concise language
- Match formality to the relationship and context
- Every email must have a clear purpose and call-to-action
- Proofread for tone before finalizing
"""

graph = create_agent(
    llm,
    tools=[draft_email, write_follow_up, write_reply, improve_email],
    name="email_drafter_agent",
    system_prompt=EMAIL_SYSTEM,
)

if __name__ == "__main__":
    requests = [
        (
            "Draft an email from Sarah (Product Manager) to John (VP Engineering) "
            "requesting a meeting to discuss Q2 roadmap priorities. Include: "
            "proposed times next week, agenda overview, and that it should take 45 minutes."
        ),
        (
            "Write a follow-up email. I sent John an email about Q2 roadmap 4 days ago "
            "and haven't heard back. My name is Sarah."
        ),
    ]

    with AgentRuntime() as runtime:
        for req in requests:
            print(f"\nRequest: {req[:80]}...")
            result = runtime.run(graph, req)
            result.print_result()
            print("-" * 60)
