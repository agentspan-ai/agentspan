# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Agent as Tool — using specialist LLM chains as tools inside an orchestrator agent.

Demonstrates:
    - Wrapping specialist LLM chains as @tool functions
    - An orchestrator agent dispatching to specialist tools via tool calls
    - create_agent handles routing automatically (no manual ToolNode/tools_condition)
    - Practical use case: orchestrator dispatching to a math agent, writing agent, and trivia agent

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


# ── Specialist tools (each uses an LCEL chain inside the tool function) ────────

@tool
def ask_math_expert(question: str) -> str:
    """Send a math problem to the math specialist and get a step-by-step answer.

    Use this for arithmetic, algebra, geometry, statistics, or any numerical problem.

    Args:
        question: The math problem to solve.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a math expert. Solve mathematical problems precisely with step-by-step reasoning."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return response.content


@tool
def ask_writing_expert(task: str) -> str:
    """Send a writing task to the writing specialist and get polished content.

    Use this for drafting, editing, improving grammar, or any writing/language task.

    Args:
        task: The writing task or text to improve.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a professional writer and editor. Help craft, improve, and polish written content."),
        ("human", "{task}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"task": task})
    return response.content


@tool
def ask_trivia_expert(question: str) -> str:
    """Look up a trivia fact or answer a general knowledge question.

    Use this for history, science, culture, sports, geography, or general knowledge.

    Args:
        question: The trivia or general knowledge question.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a trivia expert. Answer questions about history, science, culture, and general knowledge."),
        ("human", "{question}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"question": question})
    return response.content


# ── Orchestrator agent ────────────────────────────────────────────────────────

graph = create_agent(
    llm,
    tools=[ask_math_expert, ask_writing_expert, ask_trivia_expert],
    system_prompt=(
        "You are an orchestrator. Route tasks to the appropriate specialist:\n"
        "- Math problems → ask_math_expert\n"
        "- Writing/editing tasks → ask_writing_expert\n"
        "- General knowledge/trivia → ask_trivia_expert\n"
        "Combine the specialist's answer into a final helpful response."
    ),
    name="orchestrator_with_subagents",
)

if __name__ == "__main__":
    queries = [
        "What is 15% of 847, rounded to the nearest whole number?",
        "Who invented the World Wide Web and in what year?",
        "Improve this sentence: 'The meeting was went not good and people was unhappy.'",
    ]

    with AgentRuntime() as runtime:
        for query in queries:
            print(f"\nQuery: {query}")
            result = runtime.run(graph, query)
            result.print_result()
            print("-" * 60)
