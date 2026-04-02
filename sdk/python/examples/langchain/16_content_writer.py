# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Content Writer — agent with SEO, readability, and formatting tools.

Demonstrates:
    - Content quality analysis tools (readability, keyword density)
    - SEO optimization checks
    - Structured writing assistance

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

import re

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def analyze_readability(text: str) -> str:
    """Estimate readability using Flesch-Kincaid grade level approximation.

    Args:
        text: The text to analyze.
    """
    sentences = max(1, len(re.split(r"[.!?]+", text)))
    words = text.split()
    word_count = max(1, len(words))
    syllables = sum(max(1, len(re.findall(r"[aeiouAEIOU]", w))) for w in words)

    fk_grade = 0.39 * (word_count / sentences) + 11.8 * (syllables / word_count) - 15.59
    fk_grade = max(1, min(20, fk_grade))

    if fk_grade <= 6:
        level = "Elementary"
    elif fk_grade <= 10:
        level = "Middle School"
    elif fk_grade <= 14:
        level = "High School / College"
    else:
        level = "Expert / Academic"

    return (
        f"Readability: Grade {fk_grade:.1f} ({level}). "
        f"Words: {word_count}, Sentences: {sentences}, Avg words/sentence: {word_count/sentences:.1f}."
    )


@tool
def check_keyword_density(text: str, keyword: str) -> str:
    """Check how often a keyword appears in the text (density as % of total words).

    Args:
        text: The content to analyze.
        keyword: The target keyword or phrase.
    """
    words = text.lower().split()
    total = len(words)
    if total == 0:
        return "Empty text."
    count = sum(1 for w in words if keyword.lower() in w)
    density = (count / total) * 100
    recommendation = "OK" if 1 <= density <= 3 else ("Too sparse" if density < 1 else "Keyword stuffing risk")
    return f"Keyword '{keyword}': {count} occurrence(s) in {total} words ({density:.1f}%). Status: {recommendation}."


@tool
def suggest_title_variations(topic: str) -> str:
    """Generate title format suggestions for a content topic.

    Args:
        topic: The main topic of the content.
    """
    templates = [
        f"The Complete Guide to {topic.title()}",
        f"How to Master {topic.title()} in 2025",
        f"{topic.title()}: Everything You Need to Know",
        f"Top 10 {topic.title()} Tips for Beginners",
        f"Why {topic.title()} Matters More Than Ever",
    ]
    return "\n".join(f"• {t}" for t in templates)


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [analyze_readability, check_keyword_density, suggest_title_variations]

graph = create_agent(
    llm,
    tools=tools,
    name="content_writer_agent",
    system_prompt=(
        "You are a professional content strategist and writer. "
        "Help users create clear, engaging, SEO-friendly content. "
        "Use tools to analyze and improve content quality."
    ),
)

SAMPLE_CONTENT = """
Python programming is a versatile programming language used in many domains.
Python programming makes it easy to write clean code. Many developers choose
Python programming for data science tasks. Python programming also works well
for web development. If you want to learn Python programming, start with the basics.
"""

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            f"Analyze this content for readability and keyword density for 'python programming'. "
            f"Also suggest better title options for an article about Python.\n\n{SAMPLE_CONTENT}",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.16_content_writer
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
