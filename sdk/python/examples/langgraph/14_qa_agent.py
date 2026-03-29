# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""QA Agent — StateGraph that retrieves context then generates an answer.

Demonstrates:
    - Two-stage pipeline: retrieve context, then generate answer
    - Mocked retrieval step that returns relevant passages
    - Grounded answer generation using retrieved context

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
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


class State(TypedDict):
    question: str
    context: str
    answer: str


def retrieve_context(state: State) -> State:
    """Retrieve relevant context passages for the question (mocked retrieval)."""
    question_lower = state["question"].lower()
    passages = []
    for topic, docs in _DOCS.items():
        if topic in question_lower:
            passages.extend(docs)
    if not passages:
        # Fallback: return all docs as context
        for docs in _DOCS.values():
            passages.extend(docs[:1])
    context = "\n".join(f"• {p}" for p in passages)
    return {"context": context}


def generate_answer(state: State) -> State:
    """Generate an answer grounded in the retrieved context."""
    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a knowledgeable assistant. Answer the question using ONLY "
                "the provided context. If the context does not contain enough information, "
                "say so clearly. Be concise and accurate.\n\n"
                f"Context:\n{state['context']}"
            )
        ),
        HumanMessage(content=state["question"]),
    ])
    return {"answer": response.content}


builder = StateGraph(State)
builder.add_node("retrieve", retrieve_context)
builder.add_node("generate", generate_answer)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "generate")
builder.add_edge("generate", END)

graph = builder.compile(name="qa_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.14_qa_agent
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(
        # graph,
        # "What is Python and how many packages does it have?",
        # )
        # print(f"Status: {result.status}")
        # result.print_result()
