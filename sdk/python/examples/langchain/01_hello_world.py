# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Hello World — simplest LangChain agent with no tools.

Demonstrates:
    - Using create_agent from langchain.agents (returns CompiledStateGraph)
    - Running a graph with AgentRuntime
    - Basic LLM conversation without any tools

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(llm, tools=[], name="hello_world_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "Say hello and tell me a fun fact about Python programming.")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.01_hello_world
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
