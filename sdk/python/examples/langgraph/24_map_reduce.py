# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Map-Reduce — generate documents, summarize each, then reduce to a final report.

Demonstrates:
    - Generate multiple documents about a topic as a tool
    - Summarize each document individually as a tool
    - Reduce all summaries into a cohesive final report as a tool
    - The LLM orchestrates the map-reduce pipeline server-side

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
def generate_documents(topic: str) -> str:
    """Generate 3 short document snippets about the topic.

    Returns the snippets as a numbered list.

    Args:
        topic: The topic to generate document snippets about.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Generate 3 short text snippets (each 2-3 sentences) about the given topic. "
            "Format as a numbered list:\n1. ...\n2. ...\n3. ..."
        )),
        ("human", "Topic: {topic}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic})
    return response.content.strip()


@tool
def summarize_document(topic: str, document: str) -> str:
    """Summarize a single document snippet in one concise sentence.

    Args:
        topic: The overall topic for context.
        document: The document snippet to summarize.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize this text in one concise sentence."),
        ("human", "Topic: {topic}\n\nText: {document}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "document": document})
    return response.content.strip()


@tool
def reduce_summaries(topic: str, summaries: str) -> str:
    """Combine multiple document summaries into a cohesive 2-3 sentence final report.

    Args:
        topic: The topic being reported on.
        summaries: All document summaries combined (bullet points or numbered list).
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a report writer. Given the topic and a list of summaries, "
            "write a cohesive 2-3 sentence final report."
        )),
        ("human", "Topic: {topic}\n\nSummaries:\n{summaries}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "summaries": summaries})
    return response.content.strip()


MAP_REDUCE_SYSTEM = """You are a map-reduce research agent.

For each research topic:
1. Call generate_documents to create 3 document snippets
2. Call summarize_document once for EACH snippet (map phase)
3. Collect all summaries and call reduce_summaries to produce the final report (reduce phase)
4. Return the final report to the user

Make sure to summarize each document snippet individually before reducing.
"""

graph = create_agent(
    llm,
    tools=[generate_documents, summarize_document, reduce_summaries],
    name="map_reduce_agent",
    system_prompt=MAP_REDUCE_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "renewable energy breakthroughs in 2024")
        print(f"Status: {result.status}")
        result.print_result()
