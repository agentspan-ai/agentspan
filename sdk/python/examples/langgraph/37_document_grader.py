# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Document Grader — score document relevance and generate a cited answer.

Demonstrates:
    - Grading a batch of documents against a query inside tools
    - Filtering to only relevant documents
    - Generating a final answer citing sources
    - Practical use case: search result re-ranking and citation-based Q&A

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Sample document corpus
CORPUS = [
    Document(page_content="Python is a high-level, general-purpose programming language known for its readability.", metadata={"id": 1, "title": "Python Overview"}),
    Document(page_content="The Eiffel Tower is located in Paris and was built in 1889.", metadata={"id": 2, "title": "Eiffel Tower"}),
    Document(page_content="Python supports multiple programming paradigms including procedural, OOP, and functional programming.", metadata={"id": 3, "title": "Python Paradigms"}),
    Document(page_content="Machine learning is a subset of AI that enables systems to learn from data.", metadata={"id": 4, "title": "Machine Learning"}),
    Document(page_content="Python has a rich ecosystem of scientific libraries: NumPy, pandas, matplotlib, and scikit-learn.", metadata={"id": 5, "title": "Python Science Stack"}),
    Document(page_content="The Great Wall of China stretches over 13,000 miles.", metadata={"id": 6, "title": "Great Wall"}),
]


@tool
def grade_documents(query: str) -> str:
    """Score all documents 1-5 for relevance to the query and return the relevant ones.

    Documents scoring 3 or above are considered relevant.

    Args:
        query: The query to grade documents against.
    """
    scores = []
    for doc in CORPUS:
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Score the relevance of the document to the query from 1 (not relevant) to 5 (highly relevant). "
                "Respond with only a single integer."
            )),
            ("human", "Query: {query}\n\nDocument: {content}"),
        ])
        chain = prompt | llm
        response = chain.invoke({"query": query, "content": doc.page_content})
        try:
            score = int(response.content.strip()[0])
        except (ValueError, IndexError):
            score = 1
        scores.append({
            "title": doc.metadata.get("title"),
            "score": score,
            "content": doc.page_content,
        })

    relevant = [s for s in scores if s["score"] >= 3]
    if not relevant:
        return "No relevant documents found for this query."

    lines = [f"Relevant documents for '{query}':"]
    for s in relevant:
        lines.append(f"\n[{s['title']}] (score: {s['score']}/5)\n{s['content']}")
    return "\n".join(lines)


@tool
def generate_cited_answer(query: str, graded_context: str) -> str:
    """Generate a cited answer using the graded relevant documents as context.

    Args:
        query: The user's question.
        graded_context: The graded document content from grade_documents.
    """
    if "No relevant documents" in graded_context:
        return "No relevant documents were found to answer this question."

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Answer the question using only the provided sources. "
            "Cite the source title in brackets when using information from it."
        )),
        ("human", "Query: {query}\n\nSources:\n{context}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"query": query, "context": graded_context})
    return response.content.strip()


GRADER_SYSTEM = """You are a document-grading Q&A assistant.

For each question:
1. Call grade_documents to retrieve and score all documents for relevance
2. Call generate_cited_answer with the question and graded context to produce a cited answer
3. Return the answer to the user

Always base your answers only on the graded context, never on prior knowledge.
"""

graph = create_agent(
    llm,
    tools=[grade_documents, generate_cited_answer],
    name="document_grader_agent",
    system_prompt=GRADER_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What are the main features and uses of Python?")
        print(f"Status: {result.status}")
        result.print_result()
