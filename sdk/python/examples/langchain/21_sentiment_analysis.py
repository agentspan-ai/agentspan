# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sentiment Analysis — agent with lexicon-based sentiment and emotion detection.

Demonstrates:
    - Lexicon-based sentiment scoring
    - Emotion detection from text
    - Batch sentiment analysis across multiple reviews

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

POSITIVE_WORDS = {
    "excellent", "amazing", "great", "fantastic", "wonderful", "love", "perfect",
    "outstanding", "superb", "brilliant", "happy", "delighted", "impressed", "best",
    "awesome", "good", "nice", "helpful", "fast", "easy", "smooth", "recommend",
}
NEGATIVE_WORDS = {
    "terrible", "awful", "horrible", "worst", "bad", "disappointed", "poor",
    "slow", "broken", "useless", "frustrating", "annoying", "difficult", "never",
    "waste", "refund", "angry", "hate", "failed", "error", "problem", "issue",
}
EMOTION_WORDS = {
    "joy": {"happy", "joyful", "delighted", "thrilled", "ecstatic", "pleased", "wonderful"},
    "anger": {"angry", "furious", "outraged", "frustrated", "annoyed", "irritated"},
    "sadness": {"sad", "disappointed", "upset", "unhappy", "depressed", "miserable"},
    "fear": {"worried", "scared", "anxious", "nervous", "concerned", "afraid"},
    "surprise": {"shocked", "amazed", "astonished", "unexpected", "surprised", "wow"},
}


@tool
def analyze_sentiment(text: str) -> str:
    """Score the sentiment of a text using a word-matching lexicon.

    Returns a sentiment label (Positive/Negative/Neutral) and score.

    Args:
        text: The text to analyze.
    """
    words = set(text.lower().split())
    pos_count = len(words & POSITIVE_WORDS)
    neg_count = len(words & NEGATIVE_WORDS)
    total = pos_count + neg_count

    if total == 0:
        return "Sentiment: Neutral (score: 0.00) — no sentiment words detected."

    score = (pos_count - neg_count) / total
    if score > 0.2:
        label = "Positive"
    elif score < -0.2:
        label = "Negative"
    else:
        label = "Mixed/Neutral"

    return (
        f"Sentiment: {label} (score: {score:+.2f}). "
        f"Positive signals: {pos_count}, Negative signals: {neg_count}."
    )


@tool
def detect_emotions(text: str) -> str:
    """Detect dominant emotions in the text.

    Args:
        text: The text to analyze for emotional content.
    """
    words = set(text.lower().split())
    found = {}
    for emotion, vocab in EMOTION_WORDS.items():
        matches = words & vocab
        if matches:
            found[emotion] = list(matches)

    if not found:
        return "No strong emotional signals detected."

    result = "Detected emotions:\n"
    for emotion, words_found in found.items():
        result += f"  • {emotion.title()}: {', '.join(words_found)}\n"
    return result.strip()


@tool
def batch_sentiment(reviews: str) -> str:
    """Analyze sentiment for multiple newline-separated reviews.

    Args:
        reviews: Newline-separated list of review texts.
    """
    lines = [r.strip() for r in reviews.strip().split("\n") if r.strip()]
    results = []
    pos, neg, neu = 0, 0, 0
    for i, line in enumerate(lines, 1):
        words = set(line.lower().split())
        p = len(words & POSITIVE_WORDS)
        n = len(words & NEGATIVE_WORDS)
        if p > n:
            label, pos = "Positive", pos + 1
        elif n > p:
            label, neg = "Negative", neg + 1
        else:
            label, neu = "Neutral", neu + 1
        results.append(f"Review {i}: {label}")

    summary = f"\nSummary: {pos} Positive, {neg} Negative, {neu} Neutral out of {len(lines)} reviews."
    return "\n".join(results) + summary


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [analyze_sentiment, detect_emotions, batch_sentiment]

graph = create_agent(
    llm,
    tools=tools,
    name="sentiment_analysis_agent",
    system_prompt=(
        "You are a sentiment analysis assistant. Analyze text for sentiment and emotions, "
        "providing clear scores and insights. Use tools for accurate analysis."
    ),
)

REVIEWS = """The product is absolutely amazing! Fast delivery and excellent quality.
Terrible experience. The item arrived broken and customer service was unhelpful.
It's okay, nothing special. Does what it says.
I'm delighted with this purchase! Best decision I made this year."""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Analyze the sentiment and emotions in these customer reviews:\n\n{REVIEWS}",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.21_sentiment_analysis
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
