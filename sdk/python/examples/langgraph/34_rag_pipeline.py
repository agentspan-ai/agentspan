# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""RAG Pipeline — Retrieval-Augmented Generation with a StateGraph.

Demonstrates:
    - A retrieve → grade → generate pipeline
    - In-memory document store with simple keyword retrieval (no vector DB needed)
    - Grading retrieved documents for relevance before generation
    - Re-querying with a rewritten question if documents are not relevant
    - Practical use case: Q&A over a private knowledge base

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ── In-memory knowledge base ──────────────────────────────────────────────────

DOCUMENTS = [
    Document(
        page_content=(
            "LangGraph is a library for building stateful, multi-actor applications with LLMs. "
            "It extends LangChain with the ability to coordinate multiple chains (or actors) "
            "across multiple steps of computation in a cyclic manner."
        ),
        metadata={"source": "langgraph_docs", "topic": "langgraph"},
    ),
    Document(
        page_content=(
            "LangChain provides tools for building applications powered by language models. "
            "It includes components for prompt management, chains, agents, memory, and retrieval. "
            "The LCEL (LangChain Expression Language) allows composing pipelines with the | operator."
        ),
        metadata={"source": "langchain_docs", "topic": "langchain"},
    ),
    Document(
        page_content=(
            "Agentspan provides a runtime for deploying LangGraph and LangChain agents at scale. "
            "It uses Conductor as an orchestration engine and exposes agents as Conductor tasks. "
            "The AgentRuntime class handles worker registration and lifecycle management."
        ),
        metadata={"source": "agentspan_docs", "topic": "agentspan"},
    ),
    Document(
        page_content=(
            "Vector databases store high-dimensional embeddings for semantic similarity search. "
            "Popular options include Pinecone, Weaviate, Chroma, and FAISS. "
            "They are commonly used in RAG pipelines to retrieve relevant context."
        ),
        metadata={"source": "vector_db_docs", "topic": "databases"},
    ),
]


def keyword_retrieve(query: str, top_k: int = 2) -> List[Document]:
    """Simple keyword-based retrieval (no embeddings required for this example)."""
    query_words = set(query.lower().split())
    scored = []
    for doc in DOCUMENTS:
        doc_words = set(doc.page_content.lower().split())
        score = len(query_words & doc_words)
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k] if _ > 0]


# ── State and nodes ───────────────────────────────────────────────────────────

class State(TypedDict):
    question: str
    rewritten_question: Optional[str]
    documents: List[Document]
    relevant_docs: List[Document]
    generation: str
    attempts: int


def retrieve(state: State) -> State:
    query = state.get("rewritten_question") or state["question"]
    docs = keyword_retrieve(query)
    return {"documents": docs, "attempts": state.get("attempts", 0) + 1}


def grade_documents(state: State) -> State:
    """Grade each document for relevance to the question."""
    question = state["question"]
    relevant = []
    for doc in state["documents"]:
        response = llm.invoke([
            SystemMessage(
                content=(
                    "Determine if the document is relevant to the question. "
                    "Reply with 'yes' or 'no' only."
                )
            ),
            HumanMessage(content=f"Question: {question}\n\nDocument: {doc.page_content}"),
        ])
        if "yes" in response.content.lower():
            relevant.append(doc)
    return {"relevant_docs": relevant}


def rewrite_question(state: State) -> State:
    """Rewrite the question to improve retrieval."""
    response = llm.invoke([
        SystemMessage(content="Rewrite this question to be more specific for document retrieval. Return only the rewritten question."),
        HumanMessage(content=state["question"]),
    ])
    return {"rewritten_question": response.content.strip()}


def generate_answer(state: State) -> State:
    docs = state.get("relevant_docs") or state.get("documents", [])
    context = "\n\n".join(d.page_content for d in docs)
    if not context:
        context = "No relevant documents found."

    response = llm.invoke([
        SystemMessage(
            content=(
                "You are a helpful assistant. Answer the question based on the provided context. "
                "If the context doesn't contain enough information, say so."
            )
        ),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['question']}"),
    ])
    return {"generation": response.content.strip()}


def decide_to_generate(state: State) -> str:
    if state.get("relevant_docs"):
        return "generate"
    if state.get("attempts", 0) >= 2:
        return "generate"  # generate anyway after 2 attempts
    return "rewrite"


builder = StateGraph(State)
builder.add_node("retrieve", retrieve)
builder.add_node("grade", grade_documents)
builder.add_node("rewrite", rewrite_question)
builder.add_node("generate", generate_answer)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade")
builder.add_conditional_edges(
    "grade",
    decide_to_generate,
    {"generate": "generate", "rewrite": "rewrite"},
)
builder.add_edge("rewrite", "retrieve")
builder.add_edge("generate", END)

graph = builder.compile(name="rag_pipeline")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What is LangGraph and how does it differ from LangChain?")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.34_rag_pipeline
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
