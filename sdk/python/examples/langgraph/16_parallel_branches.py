# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Parallel Branches — create_agent with pros, cons, and summary tools.

Demonstrates:
    - The LLM orchestrates parallel analysis by calling pros and cons tools
    - A merge/summary tool combines both perspectives into a balanced conclusion
    - Practical use case: pros/cons analysis for any topic

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
def analyze_pros(topic: str) -> str:
    """List 3 clear advantages or pros of the given topic.

    Args:
        topic: The topic to analyze for advantages.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "List 3 clear advantages or pros. Be concise and specific."),
        ("human", "Topic: {topic}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic})
    return f"PROS:\n{response.content}"


@tool
def analyze_cons(topic: str) -> str:
    """List 3 clear disadvantages or cons of the given topic.

    Args:
        topic: The topic to analyze for disadvantages.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "List 3 clear disadvantages or cons. Be concise and specific."),
        ("human", "Topic: {topic}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic})
    return f"CONS:\n{response.content}"


@tool
def merge_and_summarize(topic: str, pros: str, cons: str) -> str:
    """Combine pros and cons into a balanced conclusion with a clear recommendation.

    Args:
        topic: The topic being analyzed.
        pros: The pros analysis text.
        cons: The cons analysis text.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You have received a pros and cons analysis. "
            "Write a balanced, one-paragraph conclusion with a clear recommendation."
        )),
        ("human", "Topic: {topic}\n\n{pros}\n\n{cons}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"topic": topic, "pros": pros, "cons": cons})
    return response.content


ANALYSIS_SYSTEM = """You are a balanced analysis assistant.

For any topic you are asked to evaluate:
1. Call analyze_pros to get the advantages
2. Call analyze_cons to get the disadvantages
3. Call merge_and_summarize with the topic, pros, and cons to produce the final balanced conclusion

Always complete all three steps.
"""

graph = create_agent(
    llm,
    tools=[analyze_pros, analyze_cons, merge_and_summarize],
    name="parallel_analysis",
    system_prompt=ANALYSIS_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "remote work for software engineers")
        print(f"Status: {result.status}")
        result.print_result()
