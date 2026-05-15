// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Example Lc4j 20 — Translation Agent
 *
 * <p>Java port of <code>sdk/python/examples/langchain/20_translation_agent.py</code>.
 *
 * <p>Demonstrates heuristic language detection, dictionary-style translation lookup,
 * and language fact retrieval. Mirrors the Python lookups exactly.
 */
public class ExampleLc4j20TranslationAgent {

    static final Map<String, List<String>> LANG_INDICATORS = new LinkedHashMap<>();
    static final Map<String, Map<String, String>> TRANSLATIONS = new LinkedHashMap<>();
    static final Map<String, String> LANGUAGE_FACTS = new LinkedHashMap<>();

    static {
        LANG_INDICATORS.put("Spanish",
            Arrays.asList("el", "la", "los", "las", "de", "en", "que", "es", "un", "una"));
        LANG_INDICATORS.put("French",
            Arrays.asList("le", "la", "les", "de", "du", "et", "est", "je", "vous", "nous"));
        LANG_INDICATORS.put("German",
            Arrays.asList("der", "die", "das", "und", "ist", "ein", "eine", "ich", "nicht", "sie"));
        LANG_INDICATORS.put("Portuguese",
            Arrays.asList("o", "a", "os", "as", "de", "do", "da", "em", "para", "com"));
        LANG_INDICATORS.put("Italian",
            Arrays.asList("il", "la", "le", "di", "del", "della", "che", "è", "un", "una"));

        TRANSLATIONS.put("hello", map(
            "Spanish", "Hola", "French", "Bonjour", "German", "Hallo",
            "Japanese", "こんにちは", "Italian", "Ciao"));
        TRANSLATIONS.put("thank you", map(
            "Spanish", "Gracias", "French", "Merci", "German", "Danke",
            "Japanese", "ありがとう", "Italian", "Grazie"));
        TRANSLATIONS.put("goodbye", map(
            "Spanish", "Adiós", "French", "Au revoir", "German", "Auf Wiedersehen",
            "Japanese", "さようなら", "Italian", "Arrivederci"));
        TRANSLATIONS.put("good morning", map(
            "Spanish", "Buenos días", "French", "Bonjour", "German", "Guten Morgen",
            "Japanese", "おはようございます", "Italian", "Buongiorno"));
        TRANSLATIONS.put("how are you", map(
            "Spanish", "¿Cómo estás?", "French", "Comment allez-vous?",
            "German", "Wie geht es Ihnen?", "Japanese", "お元気ですか？", "Italian", "Come stai?"));

        LANGUAGE_FACTS.put("Spanish",
            "Spoken by ~500M people. Official language in 20 countries. "
                + "Second most spoken native language globally.");
        LANGUAGE_FACTS.put("French",
            "Spoken by ~280M people. Official language of 29 countries. "
                + "Major language of diplomacy and international law.");
        LANGUAGE_FACTS.put("German",
            "Spoken by ~100M natives. Most spoken native language in the EU. "
                + "Rich literary tradition (Goethe, Kafka).");
        LANGUAGE_FACTS.put("Japanese",
            "Spoken by ~125M people. Uses three writing systems: Hiragana, Katakana, and Kanji.");
        LANGUAGE_FACTS.put("Mandarin",
            "Most spoken language by native speakers (~920M). Uses thousands of characters (hanzi).");
        LANGUAGE_FACTS.put("Arabic",
            "Spoken by ~310M people. Written right-to-left. Official language of 22 countries.");
    }

    private static Map<String, String> map(String... kv) {
        Map<String, String> m = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) m.put(kv[i], kv[i + 1]);
        return m;
    }

    public static class TranslationTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "detect_language",
            value = "Detect the language of the given text."
        )
        public String detectLanguage(@dev.langchain4j.agent.tool.P("text") String text) {
            String t = text == null ? "" : text.toLowerCase(Locale.ROOT);
            Set<String> words = new HashSet<>(Arrays.asList(t.split("\\s+")));
            String bestLang = "Spanish";
            int bestScore = -1;
            for (Map.Entry<String, List<String>> e : LANG_INDICATORS.entrySet()) {
                int count = 0;
                for (String w : e.getValue()) if (words.contains(w)) count++;
                if (count > bestScore) {
                    bestScore = count;
                    bestLang = e.getKey();
                }
            }
            if (bestScore >= 2) {
                int confidence = Math.min(bestScore * 20, 95);
                return "Detected language: " + bestLang + " (confidence: " + confidence + "%)";
            }
            return "Detected language: English (default — no strong indicators for other languages)";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_translation_pairs",
            value = "Look up common translations for a phrase in multiple languages."
        )
        public String getTranslationPairs(@dev.langchain4j.agent.tool.P("phrase") String phrase) {
            String p = phrase == null ? "" : phrase.toLowerCase(Locale.ROOT);
            // Mirror Python: .strip("?!.")
            while (!p.isEmpty()) {
                char c = p.charAt(p.length() - 1);
                if (c == '?' || c == '!' || c == '.') p = p.substring(0, p.length() - 1);
                else break;
            }
            while (!p.isEmpty()) {
                char c = p.charAt(0);
                if (c == '?' || c == '!' || c == '.') p = p.substring(1);
                else break;
            }

            if (TRANSLATIONS.containsKey(p)) {
                Map<String, String> pairs = TRANSLATIONS.get(p);
                StringBuilder out = new StringBuilder("Translations for '" + phrase + "':");
                for (Map.Entry<String, String> e : pairs.entrySet()) {
                    out.append("\n  ").append(e.getKey()).append(": ").append(e.getValue());
                }
                return out.toString();
            }
            return "No stored translations for '" + phrase + "'. Use the LLM to generate translations.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_language_facts",
            value = "Return interesting facts about a language."
        )
        public String getLanguageFacts(@dev.langchain4j.agent.tool.P("language") String language) {
            if (language == null || language.isEmpty()) return "No facts stored for ''.";
            String key = Character.toUpperCase(language.charAt(0)) + language.substring(1).toLowerCase(Locale.ROOT);
            String fact = LANGUAGE_FACTS.get(key);
            if (fact != null) return fact;
            return "No facts stored for '" + language + "'.";
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "translation_agent",
            Settings.LLM_MODEL,
            "You are a multilingual translation assistant. Detect languages, provide translations, "
                + "and share interesting linguistic context. Be accurate and culturally sensitive.",
            new TranslationTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "How do you say 'thank you' in Spanish, French, German, and Japanese? "
                + "Also tell me an interesting fact about Spanish."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
