// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Example Lc4j 21 — Sentiment Analysis (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/21_sentiment_analysis.py</code>.
 *
 * <p>Demonstrates lexicon-based sentiment scoring, dominant-emotion detection,
 * and batch review analysis. Lexicons mirror Python exactly.
 */
public class Example21SentimentAnalysis {

    static final Set<String> POSITIVE_WORDS = new HashSet<>(Arrays.asList(
        "excellent", "amazing", "great", "fantastic", "wonderful", "love", "perfect",
        "outstanding", "superb", "brilliant", "happy", "delighted", "impressed", "best",
        "awesome", "good", "nice", "helpful", "fast", "easy", "smooth", "recommend"
    ));

    static final Set<String> NEGATIVE_WORDS = new HashSet<>(Arrays.asList(
        "terrible", "awful", "horrible", "worst", "bad", "disappointed", "poor",
        "slow", "broken", "useless", "frustrating", "annoying", "difficult", "never",
        "waste", "refund", "angry", "hate", "failed", "error", "problem", "issue"
    ));

    static final Map<String, Set<String>> EMOTION_WORDS = new LinkedHashMap<>();

    static {
        EMOTION_WORDS.put("joy", new HashSet<>(Arrays.asList(
            "happy", "joyful", "delighted", "thrilled", "ecstatic", "pleased", "wonderful")));
        EMOTION_WORDS.put("anger", new HashSet<>(Arrays.asList(
            "angry", "furious", "outraged", "frustrated", "annoyed", "irritated")));
        EMOTION_WORDS.put("sadness", new HashSet<>(Arrays.asList(
            "sad", "disappointed", "upset", "unhappy", "depressed", "miserable")));
        EMOTION_WORDS.put("fear", new HashSet<>(Arrays.asList(
            "worried", "scared", "anxious", "nervous", "concerned", "afraid")));
        EMOTION_WORDS.put("surprise", new HashSet<>(Arrays.asList(
            "shocked", "amazed", "astonished", "unexpected", "surprised", "wow")));
    }

    static final String REVIEWS =
        "The product is absolutely amazing! Fast delivery and excellent quality.\n"
        + "Terrible experience. The item arrived broken and customer service was unhelpful.\n"
        + "It's okay, nothing special. Does what it says.\n"
        + "I'm delighted with this purchase! Best decision I made this year.";

    public static class SentimentTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "analyze_sentiment",
            value = "Score the sentiment of a text using a word-matching lexicon. "
                + "Returns a sentiment label (Positive/Negative/Neutral) and score."
        )
        public String analyzeSentiment(@dev.langchain4j.agent.tool.P("text") String text) {
            Set<String> words = tokens(text);
            int pos = countIntersect(words, POSITIVE_WORDS);
            int neg = countIntersect(words, NEGATIVE_WORDS);
            int total = pos + neg;
            if (total == 0) {
                return "Sentiment: Neutral (score: 0.00) — no sentiment words detected.";
            }
            double score = (double) (pos - neg) / total;
            String label;
            if (score > 0.2) label = "Positive";
            else if (score < -0.2) label = "Negative";
            else label = "Mixed/Neutral";

            return String.format(Locale.ROOT,
                "Sentiment: %s (score: %+.2f). Positive signals: %d, Negative signals: %d.",
                label, score, pos, neg);
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "detect_emotions",
            value = "Detect dominant emotions in the text."
        )
        public String detectEmotions(@dev.langchain4j.agent.tool.P("text") String text) {
            Set<String> words = tokens(text);
            Map<String, List<String>> found = new LinkedHashMap<>();
            for (Map.Entry<String, Set<String>> e : EMOTION_WORDS.entrySet()) {
                List<String> matches = new ArrayList<>();
                for (String w : e.getValue()) if (words.contains(w)) matches.add(w);
                if (!matches.isEmpty()) found.put(e.getKey(), matches);
            }
            if (found.isEmpty()) return "No strong emotional signals detected.";

            StringBuilder out = new StringBuilder("Detected emotions:\n");
            for (Map.Entry<String, List<String>> e : found.entrySet()) {
                String emotion = e.getKey();
                String title = Character.toUpperCase(emotion.charAt(0)) + emotion.substring(1);
                out.append("  • ").append(title).append(": ")
                    .append(String.join(", ", e.getValue())).append("\n");
            }
            return out.toString().replaceAll("\\s+$", "");
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "batch_sentiment",
            value = "Analyze sentiment for multiple newline-separated reviews."
        )
        public String batchSentiment(@dev.langchain4j.agent.tool.P("reviews") String reviews) {
            String src = reviews == null ? "" : reviews.trim();
            String[] raw = src.split("\n");
            List<String> lines = new ArrayList<>();
            for (String l : raw) {
                String s = l.trim();
                if (!s.isEmpty()) lines.add(s);
            }
            List<String> results = new ArrayList<>();
            int pos = 0, neg = 0, neu = 0;
            for (int i = 0; i < lines.size(); i++) {
                Set<String> words = tokens(lines.get(i));
                int p = countIntersect(words, POSITIVE_WORDS);
                int n = countIntersect(words, NEGATIVE_WORDS);
                String label;
                if (p > n) { label = "Positive"; pos++; }
                else if (n > p) { label = "Negative"; neg++; }
                else { label = "Neutral"; neu++; }
                results.add("Review " + (i + 1) + ": " + label);
            }
            String summary = "\nSummary: " + pos + " Positive, " + neg + " Negative, "
                + neu + " Neutral out of " + lines.size() + " reviews.";
            return String.join("\n", results) + summary;
        }
    }

    private static Set<String> tokens(String text) {
        String t = text == null ? "" : text.toLowerCase(Locale.ROOT);
        return new HashSet<>(Arrays.asList(t.split("\\s+")));
    }

    private static int countIntersect(Set<String> a, Set<String> b) {
        int n = 0;
        for (String x : a) if (b.contains(x)) n++;
        return n;
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
            model,
            "You are a sentiment analysis assistant. Analyze text for sentiment and emotions, "
                + "providing clear scores and insights. Use tools for accurate analysis.\n\n"
                + "Analyze the sentiment and emotions in these customer reviews:\n\n" + REVIEWS,
            new SentimentTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
