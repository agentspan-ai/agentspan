# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Chat History — multi-turn conversation with explicit message history.

Demonstrates:
    - Passing HumanMessage / AIMessage history into the prompt
    - Building a multi-turn context manually
    - Simulating a follow-up question that relies on prior context

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def recall_fact(topic: str) -> str:
    """Retrieve a stored fact about the given topic.

    Args:
        topic: The topic to look up (e.g., 'solar system', 'python').
    """
    facts = {
        "solar system": "The Solar System has 8 planets. Neptune is the farthest from the Sun.",
        "python": "Python was created by Guido van Rossum and first released in 1991.",
        "mars": "Mars is the fourth planet from the Sun and has two moons: Phobos and Deimos.",
        "earth": "Earth is the third planet from the Sun and the only known planet to harbor life.",
    }
    return facts.get(topic.lower(), f"No facts stored for '{topic}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [recall_fact]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful science assistant. Use tools to look up facts when needed."),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, name="chat_history_agent")

if __name__ == "__main__":
    # Simulate a multi-turn conversation by injecting prior history
    history = [
        HumanMessage(content="Tell me about the solar system."),
        AIMessage(content="The Solar System has 8 planets. Neptune is the farthest from the Sun."),
    ]

    with AgentRuntime() as runtime:
        result = runtime.run(
            executor,
            "Which planet did we just discuss that is farthest from the Sun?",
            session_id="chat-history-demo-001",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(executor)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.06_chat_history
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(executor)
