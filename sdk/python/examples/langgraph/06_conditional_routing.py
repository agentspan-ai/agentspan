# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conditional Routing — create_agent with sentiment-based routing tools.

Demonstrates:
    - Using create_agent with a system prompt that directs conditional routing behaviour
    - Tools for classifying sentiment and generating tailored responses
    - The LLM orchestrates routing logic server-side via tool calls

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents.langchain import create_agent
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def respond_to_positive(text: str) -> str:
    """Generate an enthusiastic, warm reply for a positive message.

    Args:
        text: The positive message to respond to.
    """
    return (
        f"That's wonderful to hear! Your positive energy is contagious. "
        f"Keep up the great momentum — you're doing amazing things!"
    )


@tool
def respond_to_negative(text: str) -> str:
    """Generate an empathetic, supportive reply for a negative or distressing message.

    Args:
        text: The negative message to respond to.
    """
    return (
        f"I hear you, and I'm sorry you're going through this. "
        f"Your feelings are completely valid. Remember that difficult times are temporary, "
        f"and there are people who care about you and want to help."
    )


@tool
def respond_to_neutral(text: str) -> str:
    """Generate an informative, balanced reply for a neutral message.

    Args:
        text: The neutral message to respond to.
    """
    return (
        f"Thank you for sharing that. I'd be happy to help you explore this topic further "
        f"or provide additional context if you have specific questions."
    )


ROUTER_SYSTEM = """You are a sentiment-aware assistant.
For every message:
1. Classify the sentiment (positive, negative, or neutral)
2. Based on the sentiment, call the matching response tool:
   - Positive sentiment → respond_to_positive
   - Negative sentiment → respond_to_negative
   - Neutral sentiment → respond_to_neutral
3. Return the tool's response as your answer.
"""

graph = create_agent(
    llm,
    tools=[respond_to_positive, respond_to_negative, respond_to_neutral],
    name="sentiment_router",
    system_prompt=ROUTER_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "I just got promoted at work and I'm thrilled!")
        print(f"Status: {result.status}")
        result.print_result()
