# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Document Grader — score document relevance for a query.

Demonstrates:
    - Grading a batch of documents against a query
    - Filtering to only relevant documents
    - Generating a final answer citing sources
    - Practical use case: search result re-ranking and citation-based Q&A

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ── Sample document corpus ────────────────────────────────────────────────────

CORPUS = [
    Document(page_content="Python is a high-level, general-purpose programming language known for its readability.", metadata={"id": 1, "title": "Python Overview"}),
    Document(page_content="The Eiffel Tower is located in Paris and was built in 1889.", metadata={"id": 2, "title": "Eiffel Tower"}),
    Document(page_content="Python supports multiple programming paradigms including procedural, OOP, and functional programming.", metadata={"id": 3, "title": "Python Paradigms"}),
    Document(page_content="Machine learning is a subset of AI that enables systems to learn from data.", metadata={"id": 4, "title": "Machine Learning"}),
    Document(page_content="Python has a rich ecosystem of scientific libraries: NumPy, pandas, matplotlib, and scikit-learn.", metadata={"id": 5, "title": "Python Science Stack"}),
    Document(page_content="The Great Wall of China stretches over 13,000 miles.", metadata={"id": 6, "title": "Great Wall"}),
]


class State(TypedDict):
    query: str
    documents: List[Document]
    scores: List[dict]
    relevant_docs: List[Document]
    answer: str


def retrieve_all(state: State) -> State:
    """In this example, start with the full corpus."""
    return {"documents": CORPUS}


def grade_documents(state: State) -> State:
    """Score each document 1-5 for relevance to the query."""
    query = state["query"]
    scores = []
    for doc in state["documents"]:
        response = llm.invoke([
            SystemMessage(
                content=(
                    "Score the relevance of the document to the query from 1 (not relevant) to 5 (highly relevant). "
                    "Respond with only a single integer."
                )
            ),
            HumanMessage(content=f"Query: {query}\n\nDocument: {doc.page_content}"),
        ])
        try:
            score = int(response.content.strip()[0])
        except (ValueError, IndexError):
            score = 1
        scores.append({"doc_id": doc.metadata.get("id"), "title": doc.metadata.get("title"), "score": score})

    relevant = [
        doc for doc, s in zip(state["documents"], scores) if s["score"] >= 3
    ]
    return {"scores": scores, "relevant_docs": relevant}


def generate_answer(state: State) -> State:
    relevant = state.get("relevant_docs", [])
    if not relevant:
        return {"answer": "No relevant documents found for this query."}

    context_parts = []
    for doc in relevant:
        title = doc.metadata.get("title", "Unknown")
        context_parts.append(f"[{title}]: {doc.page_content}")
    context = "\n".join(context_parts)

    response = llm.invoke([
        SystemMessage(
            content=(
                "Answer the question using only the provided sources. "
                "Cite the source title in brackets when using information from it."
            )
        ),
        HumanMessage(content=f"Query: {state['query']}\n\nSources:\n{context}"),
    ])
    return {"answer": response.content.strip()}


builder = StateGraph(State)
builder.add_node("retrieve", retrieve_all)
builder.add_node("grade", grade_documents)
builder.add_node("generate", generate_answer)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade")
builder.add_edge("grade", "generate")
builder.add_edge("generate", END)

graph = builder.compile(name="document_grader_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.langgraph.37_document_grader
        runtime.deploy(graph)
        runtime.serve(graph)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(graph, "What are the main features and uses of Python?")
        # print(f"Status: {result.status}")
        # result.print_result()
