# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Sentiment Analysis — batch sentiment analysis with aspect-based scoring.

Demonstrates:
    - Overall sentiment classification (positive/negative/neutral)
    - Aspect-based sentiment analysis (extracting specific dimensions)
    - Sentiment trends across multiple texts
    - Practical use case: product review analysis pipeline

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from typing import List

from langchain_core.tools import tool
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


@tool
def classify_sentiment(text: str) -> str:
    """Classify the overall sentiment of a text as positive, negative, or neutral.

    Returns a sentiment label with a confidence score and brief explanation.

    Args:
        text: Text to analyze for sentiment.
    """
    response = llm.invoke(
        f"Classify the sentiment of this text.\n"
        f"Return format: SENTIMENT: [positive/negative/neutral] | CONFIDENCE: [0-100%] | REASON: [one sentence]\n\n"
        f"Text: {text}"
    )
    return response.content.strip()


@tool
def aspect_sentiment(text: str, aspects: str) -> str:
    """Perform aspect-based sentiment analysis on specific dimensions.

    Args:
        text: Text to analyze.
        aspects: Comma-separated list of aspects to analyze (e.g., 'quality, price, delivery, support').
    """
    aspect_list = [a.strip() for a in aspects.split(",")]
    response = llm.invoke(
        f"Analyze the sentiment for each of these aspects in the text.\n"
        f"Aspects: {', '.join(aspect_list)}\n"
        f"For each aspect, provide: aspect: [positive/negative/neutral/not_mentioned] - quote or reason\n\n"
        f"Text: {text}"
    )
    return f"Aspect-based analysis:\n{response.content.strip()}"


@tool
def extract_key_phrases(text: str, sentiment_filter: str = "all") -> str:
    """Extract key phrases that drive the sentiment.

    Args:
        text: Text to analyze.
        sentiment_filter: Filter phrases by — 'positive', 'negative', 'all'.
    """
    filter_instruction = ""
    if sentiment_filter == "positive":
        filter_instruction = "Focus only on positive phrases."
    elif sentiment_filter == "negative":
        filter_instruction = "Focus only on negative phrases."

    response = llm.invoke(
        f"Extract the key phrases that most strongly indicate sentiment from this text. "
        f"{filter_instruction}\n"
        f"Return as a bulleted list with [+] for positive, [-] for negative phrases.\n\n"
        f"Text: {text}"
    )
    return f"Key sentiment phrases:\n{response.content.strip()}"


@tool
def batch_sentiment_summary(reviews: str) -> str:
    """Analyze multiple reviews and produce an aggregate sentiment report.

    Args:
        reviews: Reviews separated by '---' delimiter.
    """
    review_list = [r.strip() for r in reviews.split("---") if r.strip()]
    if not review_list:
        return "No reviews to analyze."

    sentiments = []
    for rev in review_list:
        response = llm.invoke(
            f"Classify: positive, negative, or neutral. One word only.\n{rev}"
        )
        sentiments.append(response.content.strip().lower())

    pos = sentiments.count("positive")
    neg = sentiments.count("negative")
    neu = sentiments.count("neutral")
    total = len(sentiments)

    return (
        f"Batch Analysis ({total} reviews):\n"
        f"  Positive: {pos} ({pos/total*100:.0f}%)\n"
        f"  Negative: {neg} ({neg/total*100:.0f}%)\n"
        f"  Neutral:  {neu} ({neu/total*100:.0f}%)\n"
        f"  Overall trend: {'mostly positive' if pos > neg else 'mostly negative' if neg > pos else 'mixed'}"
    )


SENTIMENT_SYSTEM = """You are a sentiment analysis expert.
For review analysis:
1. Start with overall sentiment classification
2. Perform aspect-based analysis for product reviews (quality, price, delivery, support)
3. Extract key positive and negative phrases
4. Provide actionable insights for the business
"""

graph = create_agent(
    llm,
    tools=[classify_sentiment, aspect_sentiment, extract_key_phrases, batch_sentiment_summary],
    name="sentiment_analysis_agent",
    system_prompt=SENTIMENT_SYSTEM,
)

SAMPLE_REVIEW = (
    "I bought the wireless headphones two weeks ago and I'm mostly happy. The sound quality "
    "is absolutely incredible — best I've heard at this price point. Battery life is great too, "
    "lasting over 30 hours. However, the build quality feels a bit cheap for a $150 product and "
    "the ear cushions started peeling after just two weeks. Customer support was responsive and "
    "offered a replacement, which I appreciated."
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Analyze this product review in detail:\n\n{SAMPLE_REVIEW}",
        )
        print(f"Status: {result.status}")
        result.print_result()
