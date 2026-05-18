// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 19 — Fact Checker
 *
 * <p>Java port of <code>sdk/python/examples/langchain/19_fact_checker.py</code>.
 *
 * <p>Demonstrates claim parsing and verification against a static knowledge base
 * with confidence scoring. Mirrors the Python KB entries and tool semantics.
 */
public class ExampleLc4j19FactChecker {

    static class KbEntry {
        final String verdict;
        final String explanation;
        final double confidence;
        final String source;

        KbEntry(String verdict, String explanation, double confidence, String source) {
            this.verdict = verdict;
            this.explanation = explanation;
            this.confidence = confidence;
            this.source = source;
        }
    }

    static final Map<String, KbEntry> KNOWLEDGE_BASE = new LinkedHashMap<>();

    static {
        KNOWLEDGE_BASE.put("great wall of china visible from space", new KbEntry(
            "FALSE",
            "The Great Wall is too narrow (~5m) to be seen from space with the naked eye. "
                + "This is a popular myth debunked by astronauts.",
            0.99,
            "NASA, Chinese astronaut Yang Liwei (2003)"
        ));
        KNOWLEDGE_BASE.put("humans use 10% of brain", new KbEntry(
            "FALSE",
            "Neuroimaging shows virtually all brain regions are active. The 10% myth has no scientific basis.",
            0.99,
            "Journal of Neuroscience, Barry Beyerstein (1999)"
        ));
        KNOWLEDGE_BASE.put("lightning never strikes twice", new KbEntry(
            "FALSE",
            "Lightning frequently strikes the same spot multiple times. "
                + "The Empire State Building is struck ~20-25 times per year.",
            0.99,
            "NOAA Lightning Safety Program"
        ));
        KNOWLEDGE_BASE.put("water conducts electricity", new KbEntry(
            "NUANCED",
            "Pure distilled water is a poor conductor. Tap water conducts electricity due to dissolved salts and minerals.",
            0.95,
            "Standard chemistry reference"
        ));
        KNOWLEDGE_BASE.put("python is compiled language", new KbEntry(
            "NUANCED",
            "Python compiles to bytecode (.pyc) but is generally considered an interpreted language due to runtime execution.",
            0.90,
            "Python documentation"
        ));
    }

    public static class FactCheckerTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "check_claim",
            value = "Look up a claim in the fact-checking knowledge base."
        )
        public String checkClaim(@dev.langchain4j.agent.tool.P("claim") String claim) {
            String claimLower = claim == null ? "" : claim.toLowerCase(Locale.ROOT);
            for (Map.Entry<String, KbEntry> e : KNOWLEDGE_BASE.entrySet()) {
                String[] keyWords = e.getKey().split("\\s+");
                boolean matched = false;
                for (String w : keyWords) {
                    if (claimLower.contains(w)) {
                        matched = true;
                        break;
                    }
                }
                if (matched) {
                    KbEntry d = e.getValue();
                    return "Verdict: " + d.verdict + "\n"
                        + "Explanation: " + d.explanation + "\n"
                        + "Confidence: " + Math.round(d.confidence * 100) + "%\n"
                        + "Source: " + d.source;
                }
            }
            String trimmed = (claim == null ? "" : claim);
            if (trimmed.length() > 80) trimmed = trimmed.substring(0, 80);
            return "No entry found for this claim. Unable to verify: '" + trimmed + "'";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "extract_claims",
            value = "Extract individual factual claims from a block of text."
        )
        public String extractClaims(@dev.langchain4j.agent.tool.P("text") String text) {
            String src = text == null ? "" : text.replace("\n", " ");
            String[] raw = src.split("\\.");
            List<String> sentences = new ArrayList<>();
            for (String s : raw) {
                String t = s.trim();
                if (t.length() > 15) sentences.add(t);
            }
            List<String> indicators = Arrays.asList(
                "is", "are", "was", "were", "never", "always", "only", "can", "cannot", "has", "have"
            );
            List<String> claims = new ArrayList<>();
            for (String sentence : sentences) {
                String padded = " " + sentence.toLowerCase(Locale.ROOT) + " ";
                boolean hit = false;
                for (String ind : indicators) {
                    if (padded.contains(" " + ind + " ")) {
                        hit = true;
                        break;
                    }
                }
                if (hit) claims.add(sentence);
            }
            if (claims.isEmpty()) return "No distinct factual claims extracted.";

            StringBuilder out = new StringBuilder();
            int n = Math.min(5, claims.size());
            out.append("Extracted ").append(claims.size()).append(" claim(s):");
            for (int i = 0; i < n; i++) {
                out.append("\n").append(i + 1).append(". ").append(claims.get(i)).append(".");
            }
            return out.toString();
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "fact_checker_agent",
            Settings.LLM_MODEL,
            "You are a rigorous fact-checker. Extract claims from text and verify them. "
                + "Be precise about what is true, false, or nuanced. Always cite sources when available.",
            new FactCheckerTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Fact-check these claims: 'You can see the Great Wall of China from space' "
                + "and 'humans only use 10% of their brain'."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
