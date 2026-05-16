// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 22 — Classification Agent
 *
 * <p>Java port of <code>sdk/python/examples/langchain/22_classification_agent.py</code>.
 *
 * <p>Demonstrates rule-based topic and intent classification with
 * confidence scoring. Keyword tables mirror Python exactly.
 */
public class ExampleLc4j22ClassificationAgent {

    static final Map<String, List<String>> TOPIC_KEYWORDS = new LinkedHashMap<>();
    static final Map<String, List<String>> INTENT_KEYWORDS = new LinkedHashMap<>();
    static final Map<String, String> CATEGORY_EXAMPLES = new LinkedHashMap<>();

    static {
        TOPIC_KEYWORDS.put("Technology", Arrays.asList(
            "software", "hardware", "ai", "algorithm", "code", "computer", "data",
            "cloud", "api", "digital"));
        TOPIC_KEYWORDS.put("Sports", Arrays.asList(
            "game", "player", "team", "score", "match", "tournament", "championship",
            "athlete", "goal", "win"));
        TOPIC_KEYWORDS.put("Finance", Arrays.asList(
            "market", "stock", "invest", "revenue", "profit", "bank", "fund",
            "dividend", "budget", "economy"));
        TOPIC_KEYWORDS.put("Health", Arrays.asList(
            "medical", "health", "doctor", "treatment", "disease", "patient", "drug",
            "hospital", "symptoms", "care"));
        TOPIC_KEYWORDS.put("Science", Arrays.asList(
            "research", "experiment", "study", "discovery", "particle", "quantum",
            "biology", "chemistry", "lab"));
        TOPIC_KEYWORDS.put("Politics", Arrays.asList(
            "government", "election", "policy", "senator", "president", "vote",
            "party", "congress", "legislation"));

        INTENT_KEYWORDS.put("Question", Arrays.asList(
            "what", "how", "why", "when", "where", "who", "which", "?"));
        INTENT_KEYWORDS.put("Request", Arrays.asList(
            "please", "can you", "could you", "help me", "i need", "i want"));
        INTENT_KEYWORDS.put("Complaint", Arrays.asList(
            "problem", "issue", "broken", "not working", "failed", "error", "wrong", "bad"));
        INTENT_KEYWORDS.put("Feedback", Arrays.asList(
            "suggest", "recommend", "think", "believe", "opinion", "feedback", "idea"));

        CATEGORY_EXAMPLES.put("Technology",
            "Example: 'The new AI model achieved state-of-the-art performance on coding benchmarks.'");
        CATEGORY_EXAMPLES.put("Sports",
            "Example: 'The team won the championship after a thrilling overtime match.'");
        CATEGORY_EXAMPLES.put("Finance",
            "Example: 'Investors are concerned about rising interest rates affecting stock valuations.'");
        CATEGORY_EXAMPLES.put("Health",
            "Example: 'Researchers discovered a new treatment for reducing symptoms of the disease.'");
        CATEGORY_EXAMPLES.put("Science",
            "Example: 'The experiment confirmed quantum entanglement across 100km of fiber optic cable.'");
        CATEGORY_EXAMPLES.put("Politics",
            "Example: 'The senator proposed new legislation to address the issue of campaign finance.'");
    }

    public static class ClassificationTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "classify_topic",
            value = "Classify text into one or more topic categories."
        )
        public String classifyTopic(@dev.langchain4j.agent.tool.P("text") String text) {
            String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
            Map<String, Integer> scores = new LinkedHashMap<>();
            for (Map.Entry<String, List<String>> e : TOPIC_KEYWORDS.entrySet()) {
                int count = 0;
                for (String kw : e.getValue()) {
                    if (lower.contains(kw)) count++;
                }
                if (count > 0) scores.put(e.getKey(), count);
            }
            if (scores.isEmpty()) {
                return "Category: General/Other (no strong topic signals detected).";
            }
            int total = scores.values().stream().mapToInt(Integer::intValue).sum();
            List<Map.Entry<String, Integer>> ranked = new ArrayList<>(scores.entrySet());
            ranked.sort(Comparator.comparingInt((Map.Entry<String, Integer> e) -> e.getValue()).reversed());

            StringBuilder out = new StringBuilder("Topic classification:");
            int limit = Math.min(3, ranked.size());
            for (int i = 0; i < limit; i++) {
                Map.Entry<String, Integer> e = ranked.get(i);
                double confidence = Math.min((double) e.getValue() / total * 100, 95.0);
                out.append("\n  • ").append(e.getKey()).append(": ")
                    .append(String.format(Locale.ROOT, "%.0f", confidence)).append("% confidence");
            }
            return out.toString();
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "classify_intent",
            value = "Detect the user's intent from the text."
        )
        public String classifyIntent(@dev.langchain4j.agent.tool.P("text") String text) {
            String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
            List<String> detected = new ArrayList<>();
            for (Map.Entry<String, List<String>> e : INTENT_KEYWORDS.entrySet()) {
                for (String kw : e.getValue()) {
                    if (lower.contains(kw)) {
                        detected.add(e.getKey());
                        break;
                    }
                }
            }
            if (detected.isEmpty()) {
                return "Intent: Informational (statement or general content).";
            }
            return "Detected intent(s): " + String.join(", ", detected);
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_category_examples",
            value = "Return example texts that belong to a given category."
        )
        public String getCategoryExamples(@dev.langchain4j.agent.tool.P("category") String category) {
            if (category == null || category.isEmpty()) return "No examples stored for ''.";
            String key = Character.toUpperCase(category.charAt(0))
                + category.substring(1).toLowerCase(Locale.ROOT);
            String example = CATEGORY_EXAMPLES.get(key);
            if (example != null) return example;
            return "No examples stored for '" + category + "'.";
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "classification_agent",
            Settings.LLM_MODEL,
            "You are a text classification assistant. Analyze text for topic and intent, "
                + "provide confidence-scored categories, and explain your classifications.",
            new ClassificationTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Classify this text: 'How can I fix the broken API integration? "
                + "The software keeps returning a 500 error and my team cannot deploy the code.'"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
