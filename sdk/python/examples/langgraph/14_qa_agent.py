# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""QA Agent — create_agent with retrieval and answer tools.

Demonstrates:
    - Two-stage pipeline: retrieve context then generate answer, modelled as tools
    - Mocked retrieval step that returns relevant passages
    - Grounded answer generation using retrieved context inside a tool

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Mock document store (simulates a vector DB retrieval)
_DOCS = {
    "python": [
        "Python is a high-level, interpreted programming language created by Guido van Rossum in 1991.",
        "Python emphasizes code readability and uses significant indentation.",
        "The Python Package Index (PyPI) hosts over 450,000 packages as of 2024.",
    ],
    "machine learning": [
        "Machine learning is a subset of AI that enables systems to learn from data without explicit programming.",
        "Supervised learning uses labeled datasets; unsupervised learning finds hidden patterns.",
        "Neural networks inspired by the brain are the foundation of deep learning.",
    ],
    "kubernetes": [
        "Kubernetes (K8s) is an open-source container orchestration system developed by Google.",
        "It automates deployment, scaling, and management of containerized applications.",
        "Kubernetes uses Pods as the smallest deployable unit.",
    ],
}


@tool
def retrieve_context(question: str) -> str:
    """Retrieve relevant context passages for a question from the knowledge base.

    Args:
        question: The question to retrieve context for.
    """
    question_lower = question.lower()
    passages = []
    for topic, docs in _DOCS.items():
        if topic in question_lower:
            passages.extend(docs)
    if not passages:
        # Fallback: return first passage from each topic
        for docs in _DOCS.values():
            passages.extend(docs[:1])
    context = "\n".join(f"• {p}" for p in passages)
    return f"Retrieved context:\n{context}"


QA_SYSTEM = """You are a knowledgeable assistant that answers questions using a knowledge base.

For each question:
1. Call retrieve_context to get relevant passages
2. Answer the question using ONLY the retrieved context
3. If the context does not contain enough information, say so clearly

Always cite the context you are drawing from and be concise and accurate.
"""

graph = create_agent(
    llm,
    tools=[retrieve_context],
    name="qa_agent",
    system_prompt=QA_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "What is Python and how many packages does it have?",
        )
        print(f"Status: {result.status}")
        result.print_result()
