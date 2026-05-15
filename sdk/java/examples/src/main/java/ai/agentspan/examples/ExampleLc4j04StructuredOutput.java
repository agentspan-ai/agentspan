// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Example Lc4j 04 — Structured Output (JSON via a tool)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/04_structured_output.py</code>.
 * The Python version uses Pydantic's {@code BaseModel} together with
 * {@code ChatOpenAI(...).with_structured_output(BookRecommendation)} to force the
 * inner LLM call to return validated, typed data.
 *
 * <p><b>LangChain4j adaptation:</b> there is no clean parity for
 * {@code with_structured_output} when the {@code @Tool}-bearing POJO is executed
 * inside Agentspan's server-side LLM loop. The closest semantically-equivalent
 * shape is to have the tool itself return a structured JSON payload that matches
 * the Pydantic schema — the LLM then receives the same structured-tool-output it
 * would have under Pydantic. Field names, types, and ranges all match the
 * {@code BookRecommendation} model in the Python source.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Defining a strongly typed payload class ({@link BookRecommendation})</li>
 *   <li>Returning structured JSON from a {@link Tool @Tool} method</li>
 *   <li>Using a custom system prompt to steer tool selection</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code AGENTSPAN_LLM_MODEL=openai/gpt-4o} (or any provider supported by the server)</li>
 *   <li>OpenAI/provider key configured in server credentials</li>
 * </ul>
 */
public class ExampleLc4j04StructuredOutput {

    /**
     * A structured book recommendation — mirrors the Pydantic
     * {@code BookRecommendation} model in the Python source. Field types and
     * ordering match 1:1.
     */
    public static class BookRecommendation {
        public String title;       // The book title
        public String author;      // The book author
        public String genre;       // The primary genre
        public double rating;      // Rating from 1.0 to 5.0
        public String summary;     // One-sentence description
        public String whyRecommended; // Why this book is recommended

        public BookRecommendation(String title, String author, String genre,
                                  double rating, String summary, String whyRecommended) {
            this.title = title;
            this.author = author;
            this.genre = genre;
            this.rating = rating;
            this.summary = summary;
            this.whyRecommended = whyRecommended;
        }

        /** Render as JSON matching {@code BookRecommendation.model_dump(indent=2)}. */
        Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("title", title);
            m.put("author", author);
            m.put("genre", genre);
            m.put("rating", rating);
            m.put("summary", summary);
            m.put("why_recommended", whyRecommended);
            return m;
        }
    }

    static class BookTools {

        @Tool(
            name = "recommend_book",
            value = "Recommend a book for the given genre, returning structured data. "
                  + "Args: genre — the book genre (e.g., 'sci-fi', 'mystery', 'history')."
        )
        public String recommendBook(@P("genre") String genre) {
            // Python: structured_llm.invoke(f"Recommend one excellent {genre} book.")
            //         returns a BookRecommendation, then model_dump(indent=2).
            // Java adaptation: stub a canonical structured payload per genre. The
            // LLM still sees JSON in exactly the same schema the Pydantic version
            // would produce.
            BookRecommendation rec = pickFor(genre);
            return toJson(rec.toMap());
        }

        private static BookRecommendation pickFor(String rawGenre) {
            String g = rawGenre == null ? "" : rawGenre.toLowerCase(Locale.ROOT).trim();
            if (g.contains("sci") || g.contains("science")) {
                return new BookRecommendation(
                    "Dune",
                    "Frank Herbert",
                    "Science Fiction",
                    4.8,
                    "A young noble's quest to control the desert planet Arrakis and its precious spice.",
                    "A genre-defining epic combining politics, ecology, and prophecy on a grand scale."
                );
            }
            if (g.contains("mystery") || g.contains("crime") || g.contains("noir")) {
                return new BookRecommendation(
                    "The Big Sleep",
                    "Raymond Chandler",
                    "Mystery",
                    4.6,
                    "Private eye Philip Marlowe untangles a blackmail case in 1930s Los Angeles.",
                    "A masterclass in hard-boiled prose and atmosphere that defined the genre."
                );
            }
            if (g.contains("history") || g.contains("non-fiction") || g.contains("nonfiction")) {
                return new BookRecommendation(
                    "Sapiens",
                    "Yuval Noah Harari",
                    "History",
                    4.5,
                    "A sweeping account of how Homo sapiens came to dominate the planet.",
                    "Bold, wide-ranging synthesis that reframes how readers think about civilization."
                );
            }
            // Default — a strong general recommendation.
            return new BookRecommendation(
                "The Lord of the Rings",
                "J. R. R. Tolkien",
                rawGenre == null || rawGenre.isEmpty() ? "Fantasy" : rawGenre,
                4.9,
                "A fellowship sets out to destroy a powerful ring and save Middle-earth.",
                "The foundational modern fantasy epic, beloved for world-building and themes of hope."
            );
        }

        /** Minimal JSON serializer — keeps the example dependency-free. */
        private static String toJson(Map<String, Object> map) {
            StringBuilder sb = new StringBuilder("{\n");
            int i = 0;
            for (Map.Entry<String, Object> e : map.entrySet()) {
                sb.append("  \"").append(e.getKey()).append("\": ");
                Object v = e.getValue();
                if (v instanceof Number || v instanceof Boolean) {
                    sb.append(v.toString());
                } else {
                    sb.append("\"").append(escape(String.valueOf(v))).append("\"");
                }
                if (++i < map.size()) sb.append(",");
                sb.append("\n");
            }
            sb.append("}");
            return sb.toString();
        }

        private static String escape(String s) {
            return s.replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "structured_output_agent",
            Settings.LLM_MODEL,
            "You are a book recommendation assistant. Use the recommend_book tool to find books.",
            new BookTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Recommend a great science fiction book and a good mystery novel."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
