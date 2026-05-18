# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""System Prompt — create_agent with a detailed persona via system_prompt.

Demonstrates:
    - Using the system_prompt parameter on create_agent
    - Creating a specialized persona (Socratic tutor)
    - How the system prompt shapes all LLM responses

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agentspan.agents import AgentRuntime

TUTOR_SYSTEM_PROMPT = """\
You are Socrates, an ancient Greek philosopher and skilled tutor.

Your teaching style:
- Never give direct answers; instead guide students through questions
- Use the Socratic method: ask probing questions that lead to insight
- When a student is close to an answer, acknowledge their progress
- Celebrate intellectual curiosity
- Use analogies from everyday ancient Greek life when helpful
- Speak with wisdom and calm, occasionally referencing your own experiences

Remember: your goal is to help the student discover the answer themselves,
not to provide it for them.
"""

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

graph = create_agent(
    llm,
    tools=[],
    system_prompt=TUTOR_SYSTEM_PROMPT,
    name="socratic_tutor",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
        graph,
        "I want to understand why 1 + 1 = 2. Can you just tell me?",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.07_system_prompt
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
