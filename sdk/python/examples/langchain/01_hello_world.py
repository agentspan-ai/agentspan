# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Hello World — simplest LangChain AgentExecutor with no tools.

Demonstrates:
    - Creating an AgentExecutor using create_tool_calling_agent
    - Running the executor with AgentRuntime
    - Basic LLM conversation without any tools

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a friendly and knowledgeable assistant."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, [], prompt)
executor = AgentExecutor(agent=agent, tools=[], name="hello_world_agent")

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(executor, "Say hello and tell me a fun fact about Python programming.")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(executor)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.01_hello_world
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(executor)
