# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Retry on Error — automatic retry logic inside a tool with exponential back-off.

Demonstrates:
    - Handling transient failures gracefully inside a @tool function
    - Tracking retry attempts within the tool
    - Practical use case: calling an unreliable external API with retries

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import random
import time

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

_MAX_ATTEMPTS = 5
_call_count = 0


@tool
def fetch_with_retry(query: str) -> str:
    """Fetch data for a query with automatic retry on transient failures.

    Retries up to 5 times with exponential back-off when a transient error occurs.
    Returns the fetched data on success, or an error message if all attempts fail.

    Args:
        query: The data query to fetch.
    """
    global _call_count
    attempt = 0
    last_error = ""

    while attempt < _MAX_ATTEMPTS:
        attempt += 1
        _call_count += 1

        try:
            # Simulate a transient failure on the first two global calls
            if _call_count <= 2 and random.random() < 0.7:
                raise ConnectionError(f"Simulated transient network error on attempt {attempt}")

            # Success path: answer the query
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Answer the question concisely."),
                ("human", "{query}"),
            ])
            chain = prompt | llm
            response = chain.invoke({"query": query})
            return f"[Succeeded after {attempt} attempt(s)]\n{response.content.strip()}"

        except ConnectionError as exc:
            last_error = str(exc)
            if attempt < _MAX_ATTEMPTS:
                wait = 0.1 * (2 ** (attempt - 1))  # exponential back-off
                time.sleep(wait)

    return f"Failed after {_MAX_ATTEMPTS} attempts. Last error: {last_error}"


graph = create_agent(
    llm,
    tools=[fetch_with_retry],
    name="retry_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What is the speed of light in meters per second?")
        print(f"Status: {result.status}")
        result.print_result()
