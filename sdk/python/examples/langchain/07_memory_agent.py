# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Memory Agent — agent with conversational context using ConversationBufferMemory.

Demonstrates:
    - Using ConversationBufferMemory to maintain context across turns
    - Injecting memory into a ChatPromptTemplate via MessagesPlaceholder
    - Stateful conversation where the agent recalls prior exchanges

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def get_user_profile(username: str) -> str:
    """Fetch the profile for a given username.

    Args:
        username: The user's login name.
    """
    profiles = {
        "alice": "Alice Chen, Software Engineer, 5 years experience, Python/Go specialist.",
        "bob": "Bob Martinez, Data Scientist, PhD in Statistics, R/Python expert.",
        "carol": "Carol Williams, Product Manager, 8 years in B2B SaaS.",
    }
    return profiles.get(username.lower(), f"No profile found for '{username}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_user_profile]

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful HR assistant. Remember information from earlier in the conversation."),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    name="memory_agent",
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            executor,
            "Look up the profile for alice and tell me about her skills.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(executor)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.07_memory_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(executor)
