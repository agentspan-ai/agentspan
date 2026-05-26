// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import org.bsc.langgraph4j.agentexecutor.AgentExecutor;

import java.util.Locale;

/**
 * Example LangGraph 06 — Conditional routing via an LLM-driven classifier tool.
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/06_conditional_routing.py</code>
 * which uses {@code add_conditional_edges} on a {@code StateGraph}. With the
 * LangGraph4j {@code AgentExecutor} pattern, conditional routing is expressed
 * by exposing a {@code classify} tool plus per-branch handler tools — the LLM
 * uses the classifier output to decide which handler to call next.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Classifier tool that returns a routing label</li>
 *   <li>Three branch handlers (positive, negative, neutral)</li>
 *   <li>Routing instructions folded into the user message</li>
 * </ul>
 */
public class Example06ConditionalRouting {

    static class SentimentTools {

        @Tool("Classify a text's sentiment. Returns exactly one of: positive, negative, neutral.")
        public String classifySentiment(@P("text") String text) {
            String t = text == null ? "" : text.toLowerCase(Locale.ROOT);
            // Tiny rule-based classifier — deterministic so the routing branches
            // are exercised consistently regardless of LLM stochasticity.
            String[] pos = {"thrilled", "great", "love", "happy", "awesome", "promoted", "excellent"};
            String[] neg = {"sad", "angry", "hate", "terrible", "awful", "broken", "frustrated"};
            for (String w : pos) if (t.contains(w)) return "positive";
            for (String w : neg) if (t.contains(w)) return "negative";
            return "neutral";
        }

        @Tool("Generate an encouraging reply for POSITIVE sentiment input.")
        public String handlePositive(@P("text") String text) {
            return "[POSITIVE BRANCH] That's wonderful to hear: " + text;
        }

        @Tool("Generate an empathetic reply for NEGATIVE sentiment input.")
        public String handleNegative(@P("text") String text) {
            return "[NEGATIVE BRANCH] I'm sorry to hear that: " + text;
        }

        @Tool("Generate an informative reply for NEUTRAL sentiment input.")
        public String handleNeutral(@P("text") String text) {
            return "[NEUTRAL BRANCH] Thanks for sharing: " + text;
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        SentimentTools tools = new SentimentTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        // Drop-in overload — fold the routing instructions into the user message.
        AgentResult result = Agentspan.run(
                agent,
                "You are a sentiment-routing agent. For every input: "
                + "1) call classify_sentiment, "
                + "2) call exactly ONE of handle_positive / handle_negative / handle_neutral "
                + "based on the classification result, "
                + "3) return the handler's output verbatim as the final answer.\n\n"
                + "I just got promoted at work and I'm thrilled!",
                tools
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
