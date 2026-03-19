# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Reflection Agent — self-critique and iterative improvement via tools.

Demonstrates:
    - A generate → reflect → improve loop modelled as tools
    - The agent decides when to stop based on the critic's verdict
    - Practical use case: essay generation with quality self-improvement

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

MAX_ITERATIONS = 3


@tool
def generate_draft(topic: str, critique: str = "") -> str:
    """Write or improve a paragraph about a topic.

    If critique is provided, improve the previous draft based on it.
    If critique is empty, write an initial draft.

    Args:
        topic: The topic to write about.
        critique: Previous critique to incorporate (empty for first draft).
    """
    if not critique:
        prompt_text = f"Write a concise, well-structured paragraph about: {topic}"
    else:
        prompt_text = (
            f"Improve this paragraph about '{topic}' based on the critique below.\n\n"
            f"Critique:\n{critique}\n\n"
            "Return only the improved paragraph."
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a skilled writer. Produce clear, engaging prose."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": prompt_text})
    return response.content.strip()


@tool
def reflect_on_draft(topic: str, draft: str) -> str:
    """Critique a paragraph for quality and return feedback.

    Returns feedback starting with 'APPROVE' if the paragraph is excellent,
    or 'REVISE' followed by specific improvements needed.

    Args:
        topic: The topic of the paragraph.
        draft: The paragraph to critique.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a rigorous editor. Critique the paragraph on:\n"
            "1. Clarity\n2. Accuracy\n3. Engagement\n4. Conciseness\n\n"
            "If the paragraph is already excellent, start your response with 'APPROVE'. "
            "Otherwise start with 'REVISE' and list specific improvements."
        )),
        ("human", "Topic: {topic}\n\nParagraph:\n{draft}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "draft": draft})
    return response.content.strip()


REFLECTION_SYSTEM = f"""You are a self-improving writing agent.

For each writing request:
1. Call generate_draft with the topic (no critique for the first draft)
2. Call reflect_on_draft to get feedback on the draft
3. If the critique starts with 'REVISE' and you have done fewer than {MAX_ITERATIONS} iterations:
   - Call generate_draft again with the topic AND the critique to improve it
   - Call reflect_on_draft again on the new draft
   - Repeat until you get 'APPROVE' or reach {MAX_ITERATIONS} total drafts
4. Return the final draft as your answer

Track the number of iterations — stop after {MAX_ITERATIONS} total drafts even if not approved.
"""

graph = create_agent(
    llm,
    tools=[generate_draft, reflect_on_draft],
    name="reflection_agent",
    system_prompt=REFLECTION_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "the importance of open-source software in modern technology",
        )
        print(f"Status: {result.status}")
        result.print_result()
