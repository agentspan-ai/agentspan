# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenAI Agent — Manager Pattern with agents-as-tools.

Demonstrates:
    - Using Agent.as_tool() to expose specialist agents as tools
    - A manager agent that delegates to specialists via tool calls
    - Differs from handoffs: manager retains control and synthesizes results

Requirements:
    - pip install openai-agents
    - Conductor server with OpenAI LLM integration configured
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agents import Agent, function_tool

from agentspan.agents import AgentRuntime

from settings import settings


# ── Specialist tools ──────────────────────────────────────────────────

@function_tool
def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of text. Returns positive, negative, or neutral."""
    positive_words = {"great", "love", "excellent", "amazing", "wonderful", "best"}
    negative_words = {"bad", "terrible", "hate", "awful", "worst", "horrible"}

    words = set(text.lower().split())
    pos = len(words & positive_words)
    neg = len(words & negative_words)

    if pos > neg:
        return f"Positive sentiment (score: {pos}/{pos + neg})"
    elif neg > pos:
        return f"Negative sentiment (score: {neg}/{pos + neg})"
    return "Neutral sentiment"


@function_tool
def extract_keywords(text: str) -> str:
    """Extract key topics and keywords from text."""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                  "to", "for", "of", "and", "or", "but", "with", "this", "that", "i"}
    words = text.lower().split()
    keywords = [w.strip(".,!?") for w in words if w.strip(".,!?") not in stop_words and len(w) > 3]
    unique = list(dict.fromkeys(keywords))[:10]
    return f"Keywords: {', '.join(unique)}"


# ── Specialist agents ─────────────────────────────────────────────────

sentiment_agent = Agent(
    name="sentiment_analyzer",
    instructions="You analyze text sentiment. Use the analyze_sentiment tool and provide a brief interpretation.",
    model=settings.llm_model,
    tools=[analyze_sentiment],
)

keyword_agent = Agent(
    name="keyword_extractor",
    instructions="You extract keywords from text. Use the extract_keywords tool and categorize the results.",
    model=settings.llm_model,
    tools=[extract_keywords],
)

# ── Manager agent ─────────────────────────────────────────────────────

manager = Agent(
    name="text_analysis_manager",
    instructions=(
        "You are a text analysis manager. When given text to analyze:\n"
        "1. Use the sentiment analyzer to understand the tone\n"
        "2. Use the keyword extractor to identify key topics\n"
        "3. Synthesize the results into a concise summary\n\n"
        "Always use both tools before providing your summary."
    ),
    model=settings.llm_model,
    tools=[
        sentiment_agent.as_tool(
            tool_name="sentiment_analyzer",
            tool_description="Analyze the sentiment of text using a specialist agent.",
        ),
        keyword_agent.as_tool(
            tool_name="keyword_extractor",
            tool_description="Extract keywords and topics from text using a specialist agent.",
        ),
    ],
)

with AgentRuntime() as runtime:
    result = runtime.run(
        manager,
        "Analyze this review: 'The new laptop is excellent! The display is amazing "
        "and the battery life is wonderful. However, the keyboard feels terrible "
        "and the trackpad is the worst I've used.'",
    )
    result.print_result()
