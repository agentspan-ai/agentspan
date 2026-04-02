# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Email Drafter — agent that composes professional emails with formatting tools.

Demonstrates:
    - Email structure and tone analysis tools
    - Subject line generation
    - Proofreading and formality adjustment

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import re

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def generate_subject_lines(context: str) -> str:
    """Generate 3 subject line options for an email based on context.

    Args:
        context: A brief description of the email purpose and recipient.
    """
    context_lower = context.lower()
    if "follow up" in context_lower or "followup" in context_lower:
        return (
            "Option 1: Following Up: [Meeting/Topic] — Next Steps\n"
            "Option 2: Quick Check-in on [Topic]\n"
            "Option 3: Re: [Previous Subject] — Any Updates?"
        )
    if "apolog" in context_lower or "sorry" in context_lower:
        return (
            "Option 1: My Sincere Apologies Regarding [Issue]\n"
            "Option 2: Addressing the Recent [Issue] — My Apologies\n"
            "Option 3: I Owe You an Apology"
        )
    if "introduc" in context_lower:
        return (
            "Option 1: Introduction: [Your Name] from [Company]\n"
            "Option 2: Nice to Connect — [Your Name]\n"
            "Option 3: Reaching Out: [Mutual Connection] Suggested We Chat"
        )
    return (
        "Option 1: [Action Required] [Topic]\n"
        "Option 2: Update on [Topic]\n"
        "Option 3: Quick Question About [Topic]"
    )


@tool
def check_email_tone(text: str) -> str:
    """Analyze the tone of an email draft and flag potential issues.

    Args:
        text: The email body to analyze.
    """
    issues = []
    aggressive_words = ["demand", "must", "immediately", "failure", "unacceptable", "ridiculous"]
    passive_aggressive = ["as I mentioned", "as previously stated", "clearly", "obviously", "simply"]

    text_lower = text.lower()
    for word in aggressive_words:
        if word in text_lower:
            issues.append(f"Potentially aggressive tone: '{word}'")
    for phrase in passive_aggressive:
        if phrase in text_lower:
            issues.append(f"Potentially passive-aggressive: '{phrase}'")

    if "!" in text and text.count("!") > 2:
        issues.append(f"Excessive exclamation marks: {text.count('!')} found")

    if not issues:
        return "Tone analysis: Professional and appropriate. No issues detected."
    return "Tone issues found:\n" + "\n".join(f"  • {i}" for i in issues)


@tool
def format_email_template(
    greeting: str,
    body: str,
    closing: str,
    sender_name: str,
) -> str:
    """Assemble a properly formatted email from components.

    Args:
        greeting: The opening line (e.g., 'Dear John,').
        body: The main body paragraphs.
        closing: The closing phrase (e.g., 'Best regards,').
        sender_name: The sender's name.
    """
    return f"{greeting}\n\n{body}\n\n{closing}\n{sender_name}"


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [generate_subject_lines, check_email_tone, format_email_template]

graph = create_agent(
    llm,
    tools=tools,
    name="email_drafter_agent",
    system_prompt=(
        "You are a professional email writing assistant. Help users draft clear, "
        "appropriate, and effective emails. Always check tone and suggest subject lines."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Draft a professional follow-up email to a client named Sarah after a product demo yesterday. "
            "Include subject line options and check the tone.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.18_email_drafter
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
