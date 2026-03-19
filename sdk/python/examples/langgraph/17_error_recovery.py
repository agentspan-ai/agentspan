# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Error Recovery — create_agent with graceful error handling in tools.

Demonstrates:
    - Catching exceptions within @tool functions for graceful degradation
    - Returning error information as a string so the LLM can handle it
    - The agent decides whether to process data or recover from the error

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
def fetch_data(query: str) -> str:
    """Attempt to fetch data for a query. May fail for certain query patterns.

    Returns fetched data on success, or an error description if the fetch fails.
    Queries containing 'fail' or 'error' will simulate a transient failure.

    Args:
        query: The data query to fetch.
    """
    try:
        if "fail" in query.lower() or "error" in query.lower():
            raise ValueError(f"Simulated fetch failure for query: '{query}'")
        return (
            f"Fetched data for '{query}': "
            "Sample dataset with 100 records, avg value 42.5, max 99, min 1."
        )
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def analyze_data(data: str) -> str:
    """Summarize fetched data in one sentence.

    Args:
        data: The fetched data string to analyze.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a data analyst. Summarize the following data in one sentence."),
        ("human", "{data}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"data": data})
    return response.content


@tool
def suggest_recovery(error_message: str, original_query: str) -> str:
    """Generate a helpful recovery message when a data fetch has failed.

    Apologizes briefly, explains what may have gone wrong, and suggests
    2 alternative approaches.

    Args:
        error_message: The error that occurred.
        original_query: The original query that failed.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "A data fetch error occurred. Apologize briefly, explain what may have gone wrong, "
            "and suggest 2 alternative approaches the user could try. Be concise."
        )),
        ("human", "Error: {error}\nOriginal query: {query}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"error": error_message, "query": original_query})
    return f"[RECOVERED FROM ERROR]\n{response.content}"


RECOVERY_SYSTEM = """You are a resilient data assistant.

For each query:
1. Call fetch_data to retrieve data
2. Check the result:
   - If the result starts with 'ERROR:' → call suggest_recovery with the error and original query
   - Otherwise → call analyze_data to summarize the successful fetch
3. Return the final result to the user
"""

graph = create_agent(
    llm,
    tools=[fetch_data, analyze_data, suggest_recovery],
    name="error_recovery_agent",
    system_prompt=RECOVERY_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        print("=== Happy path ===")
        result = runtime.run(graph, "sales data for Q4")
        print(f"Status: {result.status}")
        result.print_result()

        print("\n=== Error recovery path ===")
        result = runtime.run(graph, "intentionally fail this query")
        print(f"Status: {result.status}")
        result.print_result()
