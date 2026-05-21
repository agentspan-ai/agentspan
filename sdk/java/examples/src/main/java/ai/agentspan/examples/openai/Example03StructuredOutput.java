// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.List;

/**
 * Example OpenAi 03 — Structured Output
 *
 * <p>Java port of <code>sdk/python/examples/openai/03_structured_output.py</code>.
 *
 * <p>Demonstrates: forcing an OpenAI Agents SDK agent to return a typed
 * JSON object matching a Java record schema. The Python example uses a
 * Pydantic model; here we use a Java record and pass its simple name via
 * {@code .outputType(...)}.
 *
 * <p>Python parity gap: the Python example passes
 * {@code ModelSettings(temperature=0.3, max_tokens=1000)}. The current
 * {@link OpenAIAgent} builder does not expose model_settings, so we omit
 * those knobs — the rest of the agent shape is faithfully ported.
 *
 * <p>Expected JSON shape (matches {@link MovieList}):
 * <pre>{@code
 * {
 *   "recommendations": [
 *     {"title": "...", "year": 2014, "genre": "...", "reason": "..."}
 *   ],
 *   "theme": "..."
 * }
 * }</pre>
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example03StructuredOutput {

    /** Single movie recommendation — mirrors Python's MovieRecommendation pydantic model. */
    public record MovieRecommendation(String title, int year, String genre, String reason) {}

    /** Top-level recommendations payload — mirrors Python's MovieList pydantic model. */
    public record MovieList(List<MovieRecommendation> recommendations, String theme) {}

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("movie_recommender")
                .instructions(
                        "You are a movie recommendation expert. When asked for movie suggestions, "
                                + "return a structured list of recommendations with title, year, genre, "
                                + "and a brief reason for each recommendation. Identify the overall theme.")
                .model(Settings.LLM_MODEL)
                .outputType("MovieList")
                .build();

        AgentResult result = Agentspan.run(
                agent,
                "Recommend 3 sci-fi movies that explore the concept of artificial intelligence.");
        result.printResult();

        Agentspan.shutdown();
    }
}
