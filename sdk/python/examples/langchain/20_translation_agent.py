# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Translation Agent — multilingual translation with quality assessment.

Demonstrates:
    - Language detection
    - Translation with cultural adaptation
    - Back-translation quality check
    - Practical use case: localization pipeline for content

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from agentspan.agents.langchain import create_agent
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


SUPPORTED_LANGUAGES = {
    "spanish": "es", "french": "fr", "german": "de", "italian": "it",
    "portuguese": "pt", "japanese": "ja", "chinese": "zh", "korean": "ko",
    "arabic": "ar", "russian": "ru", "dutch": "nl", "swedish": "sv",
    "english": "en",
}


@tool
def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Args:
        text: Text whose language should be detected.
    """
    response = llm.invoke(
        f"Identify the language of this text. Return only the language name in English "
        f"(e.g., 'English', 'Spanish', 'French'): '{text}'"
    )
    return f"Detected language: {response.content.strip()}"


@tool
def translate_text(text: str, target_language: str, preserve_tone: bool = True) -> str:
    """Translate text to the target language.

    Args:
        text: Text to translate.
        target_language: Target language name (e.g., 'Spanish', 'French', 'Japanese').
        preserve_tone: Whether to preserve the original tone/formality level.
    """
    tone_instruction = "Preserve the original tone, formality, and style." if preserve_tone else "Adapt naturally to the target language's conventions."
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are a professional translator. Translate to {target_language}. {tone_instruction} Return only the translation."),
        ("human", "{text}"),
    ])
    chain = prompt | llm
    response = chain.invoke({"text": text})
    return f"[{target_language}] {response.content.strip()}"


@tool
def back_translate_check(original: str, translation: str, translated_language: str) -> str:
    """Verify translation quality by translating back to English and comparing.

    Args:
        original: The original English text.
        translation: The translation to verify.
        translated_language: The language the text was translated to.
    """
    # Translate back to English
    response = llm.invoke(
        f"Translate this {translated_language} text back to English exactly:\n{translation}"
    )
    back_translated = response.content.strip()

    # Ask LLM to compare semantic similarity
    comparison = llm.invoke(
        f"Compare these two English texts for semantic similarity.\n"
        f"Original: {original}\n"
        f"Back-translated: {back_translated}\n\n"
        f"Rate similarity as: Excellent / Good / Acceptable / Poor. "
        f"Note any significant meaning changes in one sentence."
    )
    return (
        f"Back-translation: {back_translated}\n"
        f"Quality assessment: {comparison.content.strip()}"
    )


@tool
def cultural_adaptation(text: str, target_culture: str) -> str:
    """Adapt text for a specific culture, going beyond literal translation.

    Args:
        text: English text to culturally adapt.
        target_culture: Target culture/region (e.g., 'Japanese business', 'Latin American informal').
    """
    response = llm.invoke(
        f"Adapt this text for {target_culture} audiences. "
        f"Consider: idioms, formality levels, cultural references, and local conventions. "
        f"Explain key adaptations made.\n\nText: {text}"
    )
    return f"[Cultural Adaptation for {target_culture}]\n{response.content.strip()}"


TRANSLATION_SYSTEM = """You are a professional multilingual translation assistant.
For translation requests:
1. Detect the source language if not specified
2. Translate to the requested target language
3. Perform a back-translation quality check for important content
4. Note any cultural nuances that may affect accuracy
Always prioritize meaning fidelity over word-for-word accuracy.
"""

graph = create_agent(
    llm,
    tools=[detect_language, translate_text, back_translate_check, cultural_adaptation],
    name="translation_agent",
    system_prompt=TRANSLATION_SYSTEM,
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "Translate the following to Spanish and verify the quality: "
            "'Innovation distinguishes between a leader and a follower. "
            "The best way to predict the future is to create it.'",
        )
        print(f"Status: {result.status}")
        result.print_result()
