# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Document Summarizer — multi-document summarization with different strategies.

Demonstrates:
    - Summarize-by-chunks for long documents
    - Extract key points, action items, and decisions
    - Comparing multiple summarization styles (brief, detailed, bullets)
    - Practical use case: meeting notes → executive summary pipeline

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
def brief_summary(text: str) -> str:
    """Create a 1-2 sentence executive summary of the document."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a professional summarizer. Write a concise 1-2 sentence executive summary."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return f"Brief Summary:\n{response.content.strip()}"


@tool
def bullet_summary(text: str) -> str:
    """Extract the key points as a bulleted list (5-7 points)."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract the 5-7 most important points as a bulleted list. Each bullet should be one sentence."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return f"Key Points:\n{response.content.strip()}"


@tool
def extract_action_items(text: str) -> str:
    """Extract all action items, tasks, and next steps from the document."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract all action items, tasks, and next steps. Format as: [OWNER] Action. If no owner is mentioned, use [TBD]."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return f"Action Items:\n{response.content.strip()}"


@tool
def extract_decisions(text: str) -> str:
    """Extract all decisions made in the document."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract all decisions made. Format as a numbered list. If no decisions are present, say 'No decisions recorded.'"),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return f"Decisions:\n{response.content.strip()}"


SUMMARIZER_SYSTEM = """You are a document analysis assistant. When given a document:
1. Always create a brief summary first
2. Then extract key points as bullets
3. Extract action items and decisions
4. Present all findings in a structured report format
"""

graph = create_agent(
    llm,
    tools=[brief_summary, bullet_summary, extract_action_items, extract_decisions],
    name="document_summarizer_agent",
    system_prompt=SUMMARIZER_SYSTEM,
)

MEETING_NOTES = """
Q3 Planning Meeting — Notes
Date: March 15, 2025 | Attendees: Sarah (PM), Alex (Engineering), Jordan (Design)

Sarah opened by reviewing Q2 metrics: 40% increase in user signups but 15% drop in retention.

Alex proposed migrating the database to PostgreSQL by end of April. The team agreed this would
improve query performance by ~30%. Alex will own the migration plan and have it ready by March 22.

Jordan presented three new dashboard designs. The team decided to go with Design Option B as it
scored highest in user testing. Jordan will finalize mockups by March 29 and share with
engineering for implementation scoping.

Sarah announced that the mobile app launch is pushed to Q4 due to resource constraints.
She will communicate this to stakeholders by end of week.

The team decided to implement weekly 30-minute sync meetings starting next Monday.
Jordan will set up the recurring calendar invite.

Next meeting: March 22, 2025.
"""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Please analyze and summarize these meeting notes:\n\n{MEETING_NOTES}",
        )
        print(f"Status: {result.status}")
        result.print_result()
