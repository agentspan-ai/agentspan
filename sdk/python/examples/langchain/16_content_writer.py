# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Content Writer — AI-powered content generation with brand voice guidelines.

Demonstrates:
    - Creating different content types (blog post, social media, email newsletter)
    - Adapting tone and length to the output format
    - Using tools for SEO keyword research and readability checks
    - Practical use case: automated content marketing pipeline

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)


@tool
def generate_blog_post(topic: str, word_count: int = 300, tone: str = "professional") -> str:
    """Write a blog post on a given topic.

    Args:
        topic: The blog post topic or title.
        word_count: Target word count (100-1000).
        tone: Writing tone — 'professional', 'casual', 'technical', 'inspirational'.
    """
    word_count = max(100, min(1000, word_count))
    prompt = f"Write a {tone} blog post about '{topic}' in approximately {word_count} words. Include a title, introduction, 2-3 key sections, and conclusion."
    response = llm.invoke(prompt)
    return response.content


@tool
def generate_social_post(topic: str, platform: str = "linkedin") -> str:
    """Create a social media post for a given platform.

    Args:
        topic: Topic or key message for the post.
        platform: Target platform — 'linkedin', 'twitter', 'instagram'.
    """
    guidelines = {
        "linkedin": "Professional tone, 150-300 words, include 3-5 relevant hashtags, call-to-action.",
        "twitter": "Under 280 characters, punchy and engaging, 1-2 hashtags, optional emoji.",
        "instagram": "Visual-forward caption, 100-200 words, 5-10 hashtags, emoji encouraged.",
    }
    guide = guidelines.get(platform.lower(), guidelines["linkedin"])
    prompt = f"Write a {platform} post about '{topic}'. Guidelines: {guide}"
    response = llm.invoke(prompt)
    return f"[{platform.upper()} POST]\n{response.content}"


@tool
def generate_email_subject_lines(topic: str, count: int = 5) -> str:
    """Generate compelling email subject lines for a marketing campaign.

    Args:
        topic: Email campaign topic or offer.
        count: Number of subject line variants (3-10).
    """
    count = max(3, min(10, count))
    prompt = (
        f"Generate {count} compelling email subject lines for a campaign about '{topic}'. "
        f"Make them concise (under 60 characters), varied in approach "
        f"(curiosity, urgency, benefit, question, personalization). "
        f"Number them 1-{count}."
    )
    response = llm.invoke(prompt)
    return f"Email Subject Lines for '{topic}':\n{response.content}"


@tool
def check_readability(text: str) -> str:
    """Estimate the readability level of text based on sentence and word length.

    Returns an approximate Flesch-Kincaid grade level assessment.
    """
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    words = text.split()
    if not sentences or not words:
        return "Text too short to analyze."

    avg_sentence_length = len(words) / len(sentences)
    avg_word_length = sum(len(w.strip(".,!?;:\"'")) for w in words) / len(words)

    # Rough readability estimate
    score = 206.835 - 1.015 * avg_sentence_length - 84.6 * (avg_word_length / 5)
    score = max(0, min(100, score))

    if score >= 70:
        level = "Easy (general audience)"
    elif score >= 50:
        level = "Standard (high school level)"
    elif score >= 30:
        level = "Difficult (college level)"
    else:
        level = "Very difficult (academic/professional)"

    return (
        f"Readability Analysis:\n"
        f"  Words: {len(words)}\n"
        f"  Sentences: {len(sentences)}\n"
        f"  Avg words/sentence: {avg_sentence_length:.1f}\n"
        f"  Reading level: {level}\n"
        f"  Flesch score (approx): {score:.0f}/100"
    )


WRITER_SYSTEM = """You are a professional content strategist and writer.
When creating content:
- Always match the tone to the platform and audience
- Include a clear call-to-action
- Check readability after creating long-form content
- Generate multiple options when relevant (e.g., subject lines)
"""

graph = create_agent(
    llm,
    tools=[generate_blog_post, generate_social_post, generate_email_subject_lines, check_readability],
    name="content_writer_agent",
    system_prompt=WRITER_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Create a LinkedIn post and 5 email subject lines for launching a new AI productivity tool.",
        )
        print(f"Status: {result.status}")
        result.print_result()
