# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Streaming Tokens — create_agent with streaming-aware response tool.

Demonstrates:
    - Using create_agent with AgentRuntime for streamed responses
    - The agent answers questions with thoroughness as directed by the system prompt
    - Practical use case: generating a long-form answer

    NOTE: Token-level streaming is handled by Agentspan's runtime infrastructure.
          This example shows the standard create_agent pattern for long-form answers.

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[],
    system_prompt="You are a helpful assistant. Answer thoroughly and in detail.",
    name="streaming_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Explain the concept of gradient descent in machine learning in about 150 words.",
        )
        print(f"Status: {result.status}")
        result.print_result()
