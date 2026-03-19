# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Supervisor — multi-agent supervisor pattern via tools.

Demonstrates:
    - A supervisor agent that dispatches to specialist tools (researcher, writer, editor)
    - Each specialist is a @tool that performs its focused task with an LLM call
    - The LLM supervisor orchestrates the pipeline server-side
    - Practical use case: research → writing → editing pipeline

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
def researcher(task: str) -> str:
    """Gather key facts and insights about a topic as 3-5 bullet points.

    Args:
        task: The research topic or task description.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a researcher. Gather key facts and insights about the topic in 3-5 bullet points."),
        ("human", "Topic: {task}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"task": task})
    return response.content.strip()


@tool
def writer(task: str, research: str) -> str:
    """Write a short article (3 paragraphs) based on research notes.

    Args:
        task: The article topic.
        research: Research notes to base the article on.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a writer. Using the research notes, write a short article (3 paragraphs)."),
        ("human", "Topic: {task}\n\nResearch:\n{research}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"task": task, "research": research})
    return response.content.strip()


@tool
def editor(draft: str) -> str:
    """Improve clarity, flow, and correctness of an article draft.

    Returns the polished version only.

    Args:
        draft: The article draft to edit.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an editor. Improve clarity, flow, and correctness of the article. Return the polished version only."),
        ("human", "{draft}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"draft": draft})
    return response.content.strip()


SUPERVISOR_SYSTEM = """You are a content production supervisor.

For each article request, orchestrate the production pipeline in order:
1. Call researcher with the topic to gather facts and insights
2. Call writer with the topic and the research notes to create a draft article
3. Call editor with the draft to produce the polished final article
4. Return the final polished article to the user

Always complete all three specialist tasks in sequence.
"""

graph = create_agent(
    llm,
    tools=[researcher, writer, editor],
    name="supervisor_multiagent",
    system_prompt=SUPERVISOR_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "The impact of large language models on software development")
        print(f"Status: {result.status}")
        result.print_result()
