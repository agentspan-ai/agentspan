# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent Handoff — transferring control between specialized tools.

Demonstrates:
    - A triage system prompt that routes to the right specialist tool
    - Each specialist tool has its own focused prompt and response style
    - The LLM triage agent dispatches to billing, technical, or general tools
    - Practical use case: customer service triage → specialist routing

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
def billing_specialist(user_message: str) -> str:
    """Handle a billing question professionally and helpfully.

    Use this tool for payment, invoice, charge, subscription, or refund questions.

    Args:
        user_message: The customer's billing question or complaint.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a billing specialist. Answer the customer's billing question "
            "professionally and helpfully. Keep it under 3 sentences."
        )),
        ("human", "{user_message}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"user_message": user_message})
    return f"[Billing Agent] {response.content.strip()}"


@tool
def technical_specialist(user_message: str) -> str:
    """Troubleshoot a technical issue step by step with clear, actionable guidance.

    Use this tool for software errors, connectivity problems, crashes, or configuration issues.

    Args:
        user_message: The customer's technical issue or error description.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a technical support specialist. Troubleshoot the issue step by step. "
            "Provide clear, actionable guidance in under 4 sentences."
        )),
        ("human", "{user_message}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"user_message": user_message})
    return f"[Technical Support] {response.content.strip()}"


@tool
def general_specialist(user_message: str) -> str:
    """Answer a general customer inquiry warmly and concisely.

    Use this tool for account settings, feature questions, onboarding,
    or anything that doesn't fit billing or technical categories.

    Args:
        user_message: The customer's general question or request.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a friendly general customer service agent. "
            "Help the customer with their question warmly and concisely."
        )),
        ("human", "{user_message}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"user_message": user_message})
    return f"[General Support] {response.content.strip()}"


TRIAGE_SYSTEM = """You are a customer service triage agent.

Classify each customer message and hand off to the right specialist:
- Payment, invoice, charge, subscription, or refund questions → billing_specialist
- Software errors, crashes, connectivity or configuration issues → technical_specialist
- Account settings, feature questions, or general inquiries → general_specialist

Call the appropriate tool and return its response directly.
"""

graph = create_agent(
    llm,
    tools=[billing_specialist, technical_specialist, general_specialist],
    name="agent_handoff",
    system_prompt=TRIAGE_SYSTEM,
)

if __name__ == "__main__":
    queries = [
        "I was charged twice for my subscription this month.",
        "My application keeps crashing with a segmentation fault.",
        "Can I change my account email address?",
    ]

    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            print(f"Status: {result.status}")
            result.print_result()
            print("-" * 60)
