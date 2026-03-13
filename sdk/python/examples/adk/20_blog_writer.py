#!/usr/bin/env python3

# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Blog Writer — Sequential pipeline for content creation.

Mirrors the blog-writer ADK sample. Sub-agents with output_key collaborate
in a handoff pattern: researcher → writer → editor → social media.
"""

from google.adk.agents import Agent

from agentspan.agents import AgentRuntime

from settings import settings


def main():
    def search_topic(topic: str) -> dict:
        """Search for information about a topic."""
        topics = {
            "ai": {
                "key_points": [
                    "AI adoption grew 72% in enterprises in 2024",
                    "Generative AI is transforming content creation and coding",
                    "AI safety and regulation are top policy priorities",
                ],
                "sources": ["TechReview", "AI Journal", "Industry Report 2024"],
            },
            "sustainability": {
                "key_points": [
                    "Renewable energy hit 30% of global electricity in 2024",
                    "Carbon capture technology is scaling rapidly",
                    "Green bonds market exceeded $500B",
                ],
                "sources": ["GreenTech Weekly", "Climate Report", "Energy Journal"],
            },
        }
        for key, data in topics.items():
            if key in topic.lower():
                return {"found": True, **data}
        return {
            "found": True,
            "key_points": [f"Key insight about {topic}"],
            "sources": ["General Research"],
        }

    def check_seo_keywords(topic: str) -> dict:
        """Get SEO keyword suggestions for a topic."""
        return {
            "primary_keyword": topic.lower().replace(" ", "-"),
            "related_keywords": [f"{topic} trends", f"{topic} 2025", f"best {topic} practices"],
            "search_volume": "high",
        }

    # Research agent gathers information
    researcher = Agent(
        name="blog_researcher",
        model=settings.llm_model,
        description="Researches topics and gathers key facts.",
        instruction=(
            "You are a research assistant. Use the search tool to gather information "
            "about the given topic. Present the key findings clearly."
        ),
        tools=[search_topic, check_seo_keywords],
        output_key="research_notes",
    )

    # Writer creates the blog post draft
    writer = Agent(
        name="blog_writer",
        model=settings.llm_model,
        description="Writes blog post drafts based on research.",
        instruction=(
            "You are a blog writer. Based on the research notes provided, "
            "write a short blog post (3-4 paragraphs). Include a catchy title. "
            "Incorporate SEO keywords naturally."
        ),
        output_key="blog_draft",
    )

    # Editor polishes the post
    editor = Agent(
        name="blog_editor",
        model=settings.llm_model,
        description="Edits and polishes blog posts.",
        instruction=(
            "You are a blog editor. Review and polish the blog draft. "
            "Improve clarity, flow, and engagement. Keep the same length. "
            "Output only the final polished blog post."
        ),
    )

    # Coordinator manages the pipeline
    coordinator = Agent(
        name="content_coordinator",
        model=settings.llm_model,
        instruction=(
            "You are a content coordinator. First use the researcher to gather information, "
            "then the writer to create a draft, and finally the editor to polish it. "
            "Present the final blog post to the user."
        ),
        sub_agents=[researcher, writer, editor],
    )

    with AgentRuntime() as runtime:
        result = runtime.run(
            coordinator,
            "Write a blog post about the conductor oss workflow and how its the best workflow engine for the agentic era."
            "Make sure to write at-least 5000 word and use markdown to format the content",

        )
        print(f"Status: {result.status}")
        print(f"Output: {result.output}")


if __name__ == "__main__":
    main()
