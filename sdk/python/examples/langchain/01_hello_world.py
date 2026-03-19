# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Hello World — simplest LangChain agent with no tools.

Demonstrates:
    - Creating a basic LangChain agent via create_agent (returns CompiledStateGraph)
    - Running it with AgentRuntime
    - Printing the result

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# No tools — pure LLM conversation detected as langgraph by Agentspan
graph = create_agent(llm, tools=[], name="langchain_hello_world")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Introduce yourself and tell me one interesting fact about large language models.",
        )
        print(f"Status: {result.status}")
        result.print_result()
