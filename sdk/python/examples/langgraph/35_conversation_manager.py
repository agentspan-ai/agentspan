# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conversation Manager — advanced conversation history with summarization.

Demonstrates:
    - Maintaining a sliding window of recent messages
    - Auto-summarizing older messages to stay within context limits
    - Separate system prompt and conversation turns in state
    - Practical use case: long-running chatbot that handles context limits gracefully

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import TypedDict, List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

WINDOW_SIZE = 6          # keep last N messages before summarizing
SUMMARY_THRESHOLD = 8    # summarize when history exceeds this length


class Message(TypedDict):
    role: str   # "user" | "assistant"
    content: str


class State(TypedDict):
    new_message: str
    history: List[Message]
    summary: str
    response: str


def _call_summarize_llm(conversation_text: str) -> str:
    """Call the LLM to summarize conversation text."""
    response = llm.invoke([
        SystemMessage(content="Summarize the following conversation in 2-3 sentences, preserving key facts."),
        HumanMessage(content=conversation_text),
    ])
    return response.content.strip()


def maybe_summarize(state: State) -> State:
    """Summarize old history when it exceeds the threshold.

    The LLM call is in a helper so this node compiles as a regular SIMPLE
    task — it only calls the LLM conditionally (when history is long).
    """
    history = state.get("history", [])
    if len(history) <= SUMMARY_THRESHOLD:
        return {}

    old_messages = history[:-WINDOW_SIZE]
    recent_messages = history[-WINDOW_SIZE:]

    conversation_text = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in old_messages
    )
    new_summary = _call_summarize_llm(conversation_text)

    if state.get("summary"):
        new_summary = f"{state['summary']}\n\n{new_summary}"

    return {"history": recent_messages, "summary": new_summary}


def respond(state: State) -> State:
    """Generate a response using current history + optional summary context."""
    messages = []
    system_content = "You are a helpful, friendly assistant."
    if state.get("summary"):
        system_content += f"\n\nConversation summary so far:\n{state['summary']}"
    messages.append(SystemMessage(content=system_content))

    for m in state.get("history", []):
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))

    messages.append(HumanMessage(content=state["new_message"]))

    ai_response = llm.invoke(messages)
    new_history = list(state.get("history", [])) + [
        {"role": "user", "content": state["new_message"]},
        {"role": "assistant", "content": ai_response.content},
    ]
    return {"history": new_history, "response": ai_response.content}


builder = StateGraph(State)
builder.add_node("summarize", maybe_summarize)
builder.add_node("respond", respond)
builder.add_edge(START, "summarize")
builder.add_edge("summarize", "respond")
builder.add_edge("respond", END)

graph = builder.compile(name="conversation_manager")

if __name__ == "__main__":
    turns = [
        "Hi! I'm learning about machine learning.",
        "Can you explain what neural networks are?",
        "What's the difference between supervised and unsupervised learning?",
    ]
    with AgentRuntime() as runtime:
        for turn in turns:
            result = runtime.run(graph, turn, session_id="user-session-001")
            print(f"You: {turn}")
            result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langgraph.35_conversation_manager
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)

            print()
