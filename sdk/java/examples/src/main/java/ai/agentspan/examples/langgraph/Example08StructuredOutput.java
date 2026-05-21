// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

/**
 * Example LangGraph 08 — Structured (JSON) output via a tool.
 *
 * <p>Inspired by <code>sdk/python/examples/langgraph/08_structured_output.py</code>
 * which passes a Pydantic {@code response_format} to {@code create_agent}. In
 * the LangGraph4j {@code AgentExecutor} flavour we expose a tool that returns
 * canonical JSON for the requested entity — the LLM then sees the structured
 * payload and reproduces it as the final answer.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Tool returns a strict JSON shape (no free-form prose)</li>
 *   <li>System prompt steering the agent to return the JSON verbatim</li>
 *   <li>How to approximate structured output without a Pydantic equivalent</li>
 * </ul>
 */
public class Example08StructuredOutput {

    static class ReviewTools {

        @Tool("Produce a structured JSON movie review with fields: "
                + "title, rating (0-10), pros (list), cons (list), summary, recommended (bool).")
        public String reviewMovie(@P("title") String title) {
            String t = title == null ? "Unknown" : title;
            // Deterministic structured payload — the LLM-side of this example
            // only needs to faithfully relay the JSON, which is the structured-
            // output guarantee we want to demonstrate.
            return "{\n"
                    + "  \"title\": \"" + escape(t) + "\",\n"
                    + "  \"rating\": 8.8,\n"
                    + "  \"pros\": [\"Inventive premise\", \"Strong visuals\", \"Memorable score\"],\n"
                    + "  \"cons\": [\"Dense plot\", \"Long runtime\"],\n"
                    + "  \"summary\": \"A landmark sci-fi thriller that rewards repeat viewing.\",\n"
                    + "  \"recommended\": true\n"
                    + "}";
        }

        private static String escape(String s) {
            return s.replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }

    public static void main(String[] args) {
        ChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unused"))
                .modelName("gpt-4o-mini")
                .build();

        Agent agent = LangGraphBridge.toAgentspan(
                "movie_review_agent",
                model,
                "You are a structured movie reviewer. For any movie title the user mentions, "
                + "call review_movie and return the JSON it produces VERBATIM. "
                + "Do not add commentary, do not reformat — output the JSON object only.",
                new ReviewTools()
        );

        AgentResult result = Agentspan.run(
                agent,
                "Write a review for the movie Inception (2010)."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
