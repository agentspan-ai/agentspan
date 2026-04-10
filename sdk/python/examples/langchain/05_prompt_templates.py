# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Prompt Templates — custom system prompts and persona injection.

Demonstrates:
    - Passing a rich system prompt to create_agent
    - Injecting persona, tone, and constraints into the agent
    - Using tools with a custom persona

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def get_word_definition(word: str) -> str:
    """Provide a concise definition and etymology for the given word.

    Args:
        word: The English word to define.
    """
    definitions = {
        "serendipity": "A happy accident; finding something valuable without seeking it. From Horace Walpole (1754), inspired by a Persian fairy tale.",
        "ephemeral": "Lasting for a very short time. From Greek ephemeros (lasting only a day).",
        "melancholy": "A deep, persistent sadness. From Greek melas (black) + khole (bile) — an ancient humoral concept.",
        "ubiquitous": "Present, appearing, or found everywhere. From Latin ubique (everywhere).",
        "paradigm": "A typical example or pattern; a framework of assumptions. From Greek paradeigma (pattern).",
    }
    return definitions.get(word.lower(), f"No pre-defined entry for '{word}'. Please consult a dictionary.")


@tool
def suggest_synonyms(word: str) -> str:
    """Return a comma-separated list of synonyms for the given word.

    Args:
        word: The word to find synonyms for.
    """
    synonyms = {
        "happy": "joyful, elated, content, pleased, cheerful",
        "sad": "sorrowful, melancholy, dejected, downcast, gloomy",
        "big": "large, enormous, vast, huge, immense",
        "fast": "swift, rapid, quick, speedy, hasty",
        "smart": "intelligent, clever, bright, sharp, astute",
    }
    return synonyms.get(word.lower(), f"No synonyms found for '{word}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_word_definition, suggest_synonyms]

SYSTEM_PROMPT = """You are Professor Lex, a distinguished linguistics professor with 30 years of experience.
Your communication style is:
- Erudite but accessible — you explain complex ideas clearly
- Enthusiastic about language and word origins
- Encouraging when students ask questions
- You occasionally use the words you're defining in a sentence

Always use the available tools to look up definitions and synonyms before answering."""

graph = create_agent(llm, tools=tools, name="prompt_templates_agent", system_prompt=SYSTEM_PROMPT)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(graph, "What does 'serendipity' mean? And what are some synonyms for 'happy'?")
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.05_prompt_templates
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
