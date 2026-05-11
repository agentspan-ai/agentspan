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
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Example Lc4j 23 — Recommendation Agent
 *
 * <p>Java port of <code>sdk/python/examples/langchain/23_recommendation_agent.py</code>.
 *
 * <p>Demonstrates a content-based book recommender with three tools:
 * genre filtering, preference-based scoring, and similarity ranking.
 */
public class ExampleLc4j23RecommendationAgent {

    static class Book {
        final String title;
        final String author;
        final List<String> genre;
        final List<String> themes;
        final String difficulty;

        Book(String title, String author, List<String> genre, List<String> themes, String difficulty) {
            this.title = title;
            this.author = author;
            this.genre = genre;
            this.themes = themes;
            this.difficulty = difficulty;
        }
    }

    static final List<Book> BOOK_CATALOG = Arrays.asList(
        new Book("Dune", "Frank Herbert",
            Arrays.asList("sci-fi", "adventure"),
            Arrays.asList("politics", "ecology", "religion"), "medium"),
        new Book("The Pragmatic Programmer", "Hunt & Thomas",
            Arrays.asList("technical", "non-fiction"),
            Arrays.asList("software", "career", "coding"), "medium"),
        new Book("Sapiens", "Yuval Noah Harari",
            Arrays.asList("history", "non-fiction"),
            Arrays.asList("humanity", "society", "evolution"), "easy"),
        new Book("Project Hail Mary", "Andy Weir",
            Arrays.asList("sci-fi", "adventure"),
            Arrays.asList("science", "survival", "space"), "easy"),
        new Book("Clean Code", "Robert C. Martin",
            Arrays.asList("technical", "non-fiction"),
            Arrays.asList("software", "coding", "best practices"), "medium"),
        new Book("The Name of the Wind", "Patrick Rothfuss",
            Arrays.asList("fantasy", "adventure"),
            Arrays.asList("magic", "music", "coming-of-age"), "easy"),
        new Book("Thinking, Fast and Slow", "Daniel Kahneman",
            Arrays.asList("psychology", "non-fiction"),
            Arrays.asList("decision-making", "cognition", "behavior"), "medium"),
        new Book("Neuromancer", "William Gibson",
            Arrays.asList("sci-fi", "cyberpunk"),
            Arrays.asList("technology", "hacking", "corporate power"), "hard")
    );

    public static class RecommendationTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "find_books_by_genre",
            value = "Find books matching a genre keyword."
        )
        public String findBooksByGenre(@dev.langchain4j.agent.tool.P("genre") String genre) {
            String g = genre == null ? "" : genre.toLowerCase(Locale.ROOT);
            List<Book> matches = new ArrayList<>();
            for (Book b : BOOK_CATALOG) {
                for (String bg : b.genre) {
                    if (bg.contains(g)) {
                        matches.add(b);
                        break;
                    }
                }
            }
            if (matches.isEmpty()) return "No books found for genre '" + genre + "'.";

            StringBuilder out = new StringBuilder();
            for (int i = 0; i < matches.size(); i++) {
                Book b = matches.get(i);
                if (i > 0) out.append("\n");
                out.append("• ").append(b.title).append(" by ").append(b.author)
                    .append(" (").append(String.join(", ", b.genre)).append(") — ")
                    .append(b.difficulty).append(" difficulty");
            }
            return out.toString();
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "score_book_for_preferences",
            value = "Score how well a book matches a user's preferred themes."
        )
        public String scoreBookForPreferences(
                @dev.langchain4j.agent.tool.P("title") String title,
                @dev.langchain4j.agent.tool.P("preferred_themes") String preferredThemes) {
            Book book = findByTitle(title);
            if (book == null) return "Book '" + title + "' not found in catalog.";

            String[] rawPrefs = preferredThemes == null ? new String[0] : preferredThemes.split(",");
            List<String> prefs = new ArrayList<>();
            for (String p : rawPrefs) {
                String t = p.trim().toLowerCase(Locale.ROOT);
                if (!t.isEmpty()) prefs.add(t);
            }

            List<String> matches = new ArrayList<>();
            for (String themeT : book.themes) {
                for (String p : prefs) {
                    if (themeT.contains(p)) {
                        matches.add(themeT);
                        break;
                    }
                }
            }
            double score = (double) matches.size() / Math.max(prefs.size(), 1) * 10.0;

            String matchStr = matches.isEmpty() ? "none" : String.join(", ", matches);
            return "Book: '" + book.title + "'\n"
                + "Matching themes: " + matchStr + "\n"
                + "Recommendation score: " + String.format(Locale.ROOT, "%.1f", score) + "/10\n"
                + "Difficulty: " + book.difficulty;
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "get_similar_books",
            value = "Find books similar to a given title based on shared genres and themes."
        )
        public String getSimilarBooks(@dev.langchain4j.agent.tool.P("title") String title) {
            Book source = findByTitle(title);
            if (source == null) return "Book '" + title + "' not found in catalog.";

            Set<String> srcGenres = new HashSet<>(source.genre);
            Set<String> srcThemes = new HashSet<>(source.themes);

            List<Object[]> sims = new ArrayList<>();
            for (Book b : BOOK_CATALOG) {
                if (b.title.equals(source.title)) continue;
                int genreOverlap = 0, themeOverlap = 0;
                for (String g : b.genre) if (srcGenres.contains(g)) genreOverlap++;
                for (String t : b.themes) if (srcThemes.contains(t)) themeOverlap++;
                int total = genreOverlap + themeOverlap;
                if (total > 0) sims.add(new Object[]{b, total});
            }
            if (sims.isEmpty()) return "No similar books found for '" + title + "'.";

            sims.sort(Comparator.comparingInt((Object[] x) -> -((Integer) x[1])));
            StringBuilder out = new StringBuilder("Books similar to '" + source.title + "':\n");
            int limit = Math.min(3, sims.size());
            for (int i = 0; i < limit; i++) {
                Book b = (Book) sims.get(i)[0];
                int score = (Integer) sims.get(i)[1];
                out.append("  • ").append(b.title).append(" by ").append(b.author)
                    .append(" (similarity: ").append(score).append(")\n");
            }
            return out.toString().replaceAll("\\s+$", "");
        }
    }

    private static Book findByTitle(String title) {
        if (title == null) return null;
        for (Book b : BOOK_CATALOG) {
            if (b.title.equalsIgnoreCase(title)) return b;
        }
        return null;
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "recommendation_agent",
            Settings.LLM_MODEL,
            "You are a personalized book recommendation assistant. Use tools to find, score, "
                + "and explain book recommendations based on the user's preferences.",
            new RecommendationTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "I love science fiction and I'm interested in themes of technology and survival. "
                + "Recommend a book and find something similar to 'Dune'."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
