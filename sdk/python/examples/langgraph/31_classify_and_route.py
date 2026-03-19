# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Classify and Route — create_agent with domain-specialist tools.

Demonstrates:
    - Using create_agent with a system prompt that directs classification and routing
    - Domain-specialist tools (science, history, sports, technology, cooking)
    - The LLM classifies the input and routes to the right specialist tool
    - Practical use case: smart help desk that routes to the right department

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
def answer_science(question: str) -> str:
    """Answer a science question with precise, relevant scientific context.

    Args:
        question: The science question to answer.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a science expert. Answer precisely with relevant scientific context."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return f"[Science Expert] {response.content.strip()}"


@tool
def answer_history(question: str) -> str:
    """Answer a history question with historical context and key dates.

    Args:
        question: The history question to answer.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a history expert. Provide historical context and key dates."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return f"[History Expert] {response.content.strip()}"


@tool
def answer_sports(question: str) -> str:
    """Answer a sports question with stats and context when relevant.

    Args:
        question: The sports question to answer.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a sports analyst. Give stats and context when relevant."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return f"[Sports Analyst] {response.content.strip()}"


@tool
def answer_technology(question: str) -> str:
    """Answer a technology question clearly and with technical accuracy.

    Args:
        question: The technology question to answer.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a technology expert. Be clear and technically accurate."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return f"[Tech Expert] {response.content.strip()}"


@tool
def answer_cooking(question: str) -> str:
    """Answer a cooking question with practical, delicious advice.

    Args:
        question: The cooking question to answer.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a professional chef. Give practical, delicious advice."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return f"[Chef] {response.content.strip()}"


ROUTER_SYSTEM = """You are a smart question router.

Classify each question into one of these categories, then call the matching tool:
- Science questions (physics, chemistry, biology, etc.) → answer_science
- History questions (events, dates, historical figures) → answer_history
- Sports questions (games, athletes, stats) → answer_sports
- Technology questions (software, hardware, computing) → answer_technology
- Cooking questions (recipes, ingredients, techniques) → answer_cooking

Call exactly one specialist tool and return its response.
"""

graph = create_agent(
    llm,
    tools=[answer_science, answer_history, answer_sports, answer_technology, answer_cooking],
    name="classify_and_route_agent",
    system_prompt=ROUTER_SYSTEM,
)

if __name__ == "__main__":
    questions = [
        "What is photosynthesis?",
        "When did World War II end?",
        "Who has won the most Grand Slam tennis titles?",
        "What is Kubernetes?",
        "How do I make a perfect risotto?",
    ]

    with AgentRuntime() as runtime:
        for q in questions:
            print(f"\nQ: {q}")
            result = runtime.run(graph, q)
            result.print_result()
