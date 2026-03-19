# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""RAG Pipeline — Retrieval-Augmented Generation as tools.

Demonstrates:
    - A retrieve → grade → generate pipeline modelled as tools
    - In-memory document store with simple keyword retrieval (no vector DB needed)
    - Grading retrieved documents for relevance inside a tool
    - Re-querying with a rewritten question if documents are not relevant
    - The LLM agent orchestrates the RAG flow server-side

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# In-memory knowledge base
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


def _keyword_retrieve(query: str, top_k: int = 2) -> List[Document]:
    """Simple keyword-based retrieval (no embeddings required for this example)."""
    query_words = set(query.lower().split())
    scored = []
    for doc in DOCUMENTS:
        doc_words = set(doc.page_content.lower().split())
        score = len(query_words & doc_words)
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored[:top_k] if score > 0]


@tool
def retrieve_documents(question: str) -> str:
    """Retrieve the most relevant documents from the knowledge base for a question.

    Uses keyword-based retrieval. Returns the content of matched documents.

    Args:
        question: The question to retrieve documents for.
    """
    docs = _keyword_retrieve(question)
    if not docs:
        return "No documents found for this query."
    parts = []
    for i, doc in enumerate(docs, 1):
        parts.append(f"[Doc {i} — {doc.metadata.get('topic', 'unknown')}]\n{doc.page_content}")
    return "\n\n".join(parts)


@tool
def grade_and_generate(question: str, context: str) -> str:
    """Grade the retrieved context for relevance and generate a grounded answer.

    If the context is relevant, generates an answer citing the sources.
    If not relevant, indicates that re-retrieval with a rewritten question is needed.

    Args:
        question: The user's question.
        context: Retrieved document content to assess and use for answering.
    """
    # Grade relevance
    grade_prompt = ChatPromptTemplate.from_messages([
        ("system", "Determine if the context contains enough information to answer the question. Reply with 'yes' or 'no' only."),
        ("human", "Question: {question}\n\nContext: {context}"),
    ])
    grade_chain = grade_prompt | llm
    grade = grade_chain.invoke({"question": question, "context": context})

    if "no" in grade.content.lower():
        return "INSUFFICIENT_CONTEXT: The retrieved documents do not contain enough information to answer this question."

    # Generate answer
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a helpful assistant. Answer the question based on the provided context. "
            "If the context doesn't contain enough information, say so."
        )),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ])
    answer_chain = answer_prompt | llm
    response = answer_chain.invoke({"question": question, "context": context})
    return response.content.strip()


@tool
def rewrite_question(question: str) -> str:
    """Rewrite a question to improve document retrieval.

    Use this when initial retrieval did not find sufficient context.

    Args:
        question: The original question to rewrite.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Rewrite this question to be more specific for document retrieval. Return only the rewritten question."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return response.content.strip()


RAG_SYSTEM = """You are a RAG (Retrieval-Augmented Generation) assistant.

For each question:
1. Call retrieve_documents to get relevant context
2. Call grade_and_generate with the question and retrieved context
   - If the result starts with 'INSUFFICIENT_CONTEXT':
     a. Call rewrite_question to get a better query
     b. Call retrieve_documents again with the rewritten question
     c. Call grade_and_generate again with the new context
3. Return the final answer to the user

Never make up information — only answer based on retrieved context.
"""

graph = create_agent(
    llm,
    tools=[retrieve_documents, grade_and_generate, rewrite_question],
    name="rag_pipeline",
    system_prompt=RAG_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What is LangGraph and how does it differ from LangChain?")
        print(f"Status: {result.status}")
        result.print_result()
