# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Classification Agent — multi-label text classification pipeline.

Demonstrates:
    - Hierarchical classification (coarse → fine-grained)
    - Zero-shot classification with confidence scores
    - Multi-label classification (text can belong to multiple categories)
    - Practical use case: support ticket routing and prioritization

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Ticket classification taxonomy
DEPARTMENTS = ["Engineering", "Billing", "Sales", "HR", "Legal", "Operations"]
PRIORITIES = ["Critical", "High", "Medium", "Low"]
ISSUE_TYPES = ["Bug", "Feature Request", "Question", "Complaint", "Compliment", "Incident"]


@tool
def classify_department(ticket: str) -> str:
    """Classify which department should handle this support ticket.

    Args:
        ticket: The support ticket text to classify.
    """
    departments_str = ", ".join(DEPARTMENTS)
    response = llm.invoke(
        f"Classify this support ticket into the most appropriate department. "
        f"Departments: {departments_str}\n"
        f"Return: DEPARTMENT: [name] | CONFIDENCE: [0-100%] | REASON: [brief]\n\n"
        f"Ticket: {ticket}"
    )
    return response.content.strip()


@tool
def classify_priority(ticket: str) -> str:
    """Assign a priority level to a support ticket.

    Priority levels:
    - Critical: Service down, data loss, security breach
    - High: Major feature broken, significant business impact
    - Medium: Minor feature issue, workaround available
    - Low: Enhancement request, cosmetic issue

    Args:
        ticket: The support ticket text.
    """
    response = llm.invoke(
        f"Assign a priority level to this support ticket.\n"
        f"Levels: Critical (outage/data loss), High (major issue), Medium (minor issue), Low (enhancement)\n"
        f"Return: PRIORITY: [level] | REASON: [one sentence]\n\n"
        f"Ticket: {ticket}"
    )
    return response.content.strip()


@tool
def classify_issue_type(ticket: str) -> str:
    """Classify the type of issue described in the ticket.

    Args:
        ticket: The support ticket text.
    """
    types_str = ", ".join(ISSUE_TYPES)
    response = llm.invoke(
        f"Classify the type of issue. A ticket may have multiple types.\n"
        f"Issue types: {types_str}\n"
        f"Return the top 1-2 applicable types with confidence: TYPE1 (XX%), TYPE2 (YY%)\n\n"
        f"Ticket: {ticket}"
    )
    return response.content.strip()


@tool
def suggest_response_template(department: str, issue_type: str) -> str:
    """Generate a response template for a given department and issue type.

    Args:
        department: Department handling the ticket.
        issue_type: Type of issue (Bug, Question, etc.).
    """
    response = llm.invoke(
        f"Write a brief, professional acknowledgment template for a {department} {issue_type} ticket. "
        f"Include: acknowledgment, expected response time, and next steps. "
        f"Keep it under 100 words. Use [CUSTOMER_NAME] and [TICKET_ID] as placeholders."
    )
    return f"Response template:\n{response.content.strip()}"


CLASSIFIER_SYSTEM = """You are a support ticket classification specialist.
For each ticket:
1. Classify the department
2. Assign priority level
3. Identify the issue type
4. Suggest an appropriate response template
5. Provide a classification summary with routing recommendation
"""

graph = create_agent(
    llm,
    tools=[classify_department, classify_priority, classify_issue_type, suggest_response_template],
    name="classification_agent",
    system_prompt=CLASSIFIER_SYSTEM,
)

SAMPLE_TICKETS = [
    "URGENT: Our entire production API is down! All requests are returning 500 errors since 2am. We're losing thousands of dollars per minute. Need immediate help!",
    "Hi, I was charged twice for my subscription this month. Invoice #12345 shows two charges of $99 each. Please refund the duplicate.",
]

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        for ticket in SAMPLE_TICKETS:
            print(f"\nTicket: {ticket[:80]}...")
            result = runtime.run(graph, f"Classify and route this support ticket:\n\n{ticket}")
            result.print_result()
            print("-" * 60)
