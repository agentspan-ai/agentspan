// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 05 — Prompt Templates / Persona Injection
 *
 * <p>Java port of <code>sdk/python/examples/langchain/05_prompt_templates.py</code>.
 * Injects a rich persona (Professor Lex) via the system prompt and exposes two
 * vocabulary tools.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Passing a rich system prompt to {@link LangChain4jAgent#from}</li>
 *   <li>Injecting persona, tone, and constraints into the agent</li>
 *   <li>Using tools alongside a custom persona</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code AGENTSPAN_LLM_MODEL=openai/gpt-4o} (or any provider supported by the server)</li>
 *   <li>OpenAI/provider key configured in server credentials</li>
 * </ul>
 */
public class ExampleLc4j05PromptTemplates {

    static class LexiconTools {

        private static final Map<String, String> DEFINITIONS = Map.of(
            "serendipity", "A happy accident; finding something valuable without seeking it. "
                + "From Horace Walpole (1754), inspired by a Persian fairy tale.",
            "ephemeral",   "Lasting for a very short time. From Greek ephemeros (lasting only a day).",
            "melancholy",  "A deep, persistent sadness. From Greek melas (black) + khole (bile) — "
                + "an ancient humoral concept.",
            "ubiquitous",  "Present, appearing, or found everywhere. From Latin ubique (everywhere).",
            "paradigm",    "A typical example or pattern; a framework of assumptions. "
                + "From Greek paradeigma (pattern)."
        );

        private static final Map<String, String> SYNONYMS = Map.of(
            "happy", "joyful, elated, content, pleased, cheerful",
            "sad",   "sorrowful, melancholy, dejected, downcast, gloomy",
            "big",   "large, enormous, vast, huge, immense",
            "fast",  "swift, rapid, quick, speedy, hasty",
            "smart", "intelligent, clever, bright, sharp, astute"
        );

        @Tool(
            name = "get_word_definition",
            value = "Provide a concise definition and etymology for the given word. "
                  + "Args: word — the English word to define."
        )
        public String getWordDefinition(@P("word") String word) {
            String key = word == null ? "" : word.toLowerCase(Locale.ROOT);
            return DEFINITIONS.getOrDefault(
                key,
                "No pre-defined entry for '" + word + "'. Please consult a dictionary."
            );
        }

        @Tool(
            name = "suggest_synonyms",
            value = "Return a comma-separated list of synonyms for the given word. "
                  + "Args: word — the word to find synonyms for."
        )
        public String suggestSynonyms(@P("word") String word) {
            String key = word == null ? "" : word.toLowerCase(Locale.ROOT);
            return SYNONYMS.getOrDefault(key, "No synonyms found for '" + word + "'.");
        }
    }

    private static final String SYSTEM_PROMPT =
        "You are Professor Lex, a distinguished linguistics professor with 30 years of experience.\n"
        + "Your communication style is:\n"
        + "- Erudite but accessible — you explain complex ideas clearly\n"
        + "- Enthusiastic about language and word origins\n"
        + "- Encouraging when students ask questions\n"
        + "- You occasionally use the words you're defining in a sentence\n\n"
        + "Always use the available tools to look up definitions and synonyms before answering.";

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "prompt_templates_agent",
            Settings.LLM_MODEL,
            SYSTEM_PROMPT,
            new LexiconTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "What does 'serendipity' mean? And what are some synonyms for 'happy'?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
