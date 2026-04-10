# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Translation Agent — language detection, translation, and back-translation verification.

Demonstrates:
    - Language detection from text characteristics
    - Multi-language translation tools
    - Back-translation for quality verification

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - OPENAI_API_KEY for ChatOpenAI
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from agentspan.agents import AgentRuntime


@tool
def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Args:
        text: The text whose language should be detected.
    """
    # Simple heuristic detection based on common words/characters
    text_lower = text.lower()

    lang_indicators = {
        "Spanish": ["el", "la", "los", "las", "de", "en", "que", "es", "un", "una"],
        "French": ["le", "la", "les", "de", "du", "et", "est", "je", "vous", "nous"],
        "German": ["der", "die", "das", "und", "ist", "ein", "eine", "ich", "nicht", "sie"],
        "Portuguese": ["o", "a", "os", "as", "de", "do", "da", "em", "para", "com"],
        "Italian": ["il", "la", "le", "di", "del", "della", "che", "è", "un", "una"],
    }

    words = set(text_lower.split())
    scores = {lang: sum(1 for w in indicators if w in words) for lang, indicators in lang_indicators.items()}
    best_lang = max(scores, key=scores.get)

    if scores[best_lang] >= 2:
        return f"Detected language: {best_lang} (confidence: {min(scores[best_lang]*20, 95)}%)"
    return "Detected language: English (default — no strong indicators for other languages)"


@tool
def get_translation_pairs(phrase: str) -> str:
    """Look up common translations for a phrase in multiple languages.

    Args:
        phrase: The English phrase to translate.
    """
    translations = {
        "hello": {"Spanish": "Hola", "French": "Bonjour", "German": "Hallo", "Japanese": "こんにちは", "Italian": "Ciao"},
        "thank you": {"Spanish": "Gracias", "French": "Merci", "German": "Danke", "Japanese": "ありがとう", "Italian": "Grazie"},
        "goodbye": {"Spanish": "Adiós", "French": "Au revoir", "German": "Auf Wiedersehen", "Japanese": "さようなら", "Italian": "Arrivederci"},
        "good morning": {"Spanish": "Buenos días", "French": "Bonjour", "German": "Guten Morgen", "Japanese": "おはようございます", "Italian": "Buongiorno"},
        "how are you": {"Spanish": "¿Cómo estás?", "French": "Comment allez-vous?", "German": "Wie geht es Ihnen?", "Japanese": "お元気ですか？", "Italian": "Come stai?"},
    }

    phrase_lower = phrase.lower().strip("?!.")
    if phrase_lower in translations:
        pairs = translations[phrase_lower]
        result = f"Translations for '{phrase}':\n"
        result += "\n".join(f"  {lang}: {trans}" for lang, trans in pairs.items())
        return result
    return f"No stored translations for '{phrase}'. Use the LLM to generate translations."


@tool
def get_language_facts(language: str) -> str:
    """Return interesting facts about a language.

    Args:
        language: The language name (e.g., 'Spanish', 'Mandarin').
    """
    facts = {
        "Spanish": "Spoken by ~500M people. Official language in 20 countries. Second most spoken native language globally.",
        "French": "Spoken by ~280M people. Official language of 29 countries. Major language of diplomacy and international law.",
        "German": "Spoken by ~100M natives. Most spoken native language in the EU. Rich literary tradition (Goethe, Kafka).",
        "Japanese": "Spoken by ~125M people. Uses three writing systems: Hiragana, Katakana, and Kanji.",
        "Mandarin": "Most spoken language by native speakers (~920M). Uses thousands of characters (hanzi).",
        "Arabic": "Spoken by ~310M people. Written right-to-left. Official language of 22 countries.",
    }
    return facts.get(language.title(), f"No facts stored for '{language}'.")


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [detect_language, get_translation_pairs, get_language_facts]

graph = create_agent(
    llm,
    tools=tools,
    name="translation_agent",
    system_prompt=(
        "You are a multilingual translation assistant. Detect languages, provide translations, "
        "and share interesting linguistic context. Be accurate and culturally sensitive."
    ),
)

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            graph,
            "How do you say 'thank you' in Spanish, French, German, and Japanese? Also tell me an interesting fact about Spanish.",
        )
        print(f"Status: {result.status}")
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(graph)
        # CLI alternative:
        # agentspan deploy --package examples.langchain.20_translation_agent
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(graph)
