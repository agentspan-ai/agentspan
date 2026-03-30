// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.Strategy;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Example 38 — Tech Trend Analyzer (multi-agent research pipeline)
 *
 * <p>Compares two programming languages using real data from:
 * <ul>
 *   <li>HackerNews (community discussion via Algolia search API)</li>
 *   <li>PyPI Stats (Python package downloads)</li>
 *   <li>NPM (JavaScript package downloads)</li>
 * </ul>
 *
 * <pre>
 * researcher → analyst → summarizer
 * </pre>
 *
 * <ul>
 *   <li>researcher: Fetches HackerNews stories for both languages</li>
 *   <li>analyst: Fetches package download stats and compares numbers</li>
 *   <li>summarizer: Produces a final report</li>
 * </ul>
 */
public class Example38TechTrends {

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    static class ResearcherTools {
        @Tool(name = "search_hackernews", description = "Search HackerNews for stories about a technology topic")
        public Map<String, Object> searchHackernews(String query, int maxResults) {
            try {
                String encoded = URLEncoder.encode(query, StandardCharsets.UTF_8);
                int limit = Math.min(maxResults > 0 ? maxResults : 5, 10);
                String url = "https://hn.algolia.com/api/v1/search?query=" + encoded
                    + "&tags=story&hitsPerPage=" + limit;
                String body = get(url);
                // Parse minimally: extract story titles and counts
                int hitCount = countOccurrences(body, "\"objectID\"");
                String snippet = body.length() > 500 ? body.substring(0, 500) + "..." : body;
                return Map.of(
                    "query", query,
                    "stories_found", hitCount,
                    "data_preview", snippet
                );
            } catch (Exception e) {
                return Map.of("query", query, "error", e.getMessage(), "stories_found", 0);
            }
        }
    }

    static class AnalystTools {
        @Tool(name = "fetch_pypi_downloads", description = "Fetch monthly download stats for a PyPI package")
        public Map<String, Object> fetchPypiDownloads(String packageName) {
            try {
                String url = "https://pypistats.org/api/packages/" + packageName + "/recent";
                String body = get(url);
                // Extract download number from JSON
                int idx = body.indexOf("\"last_month\":");
                if (idx >= 0) {
                    String after = body.substring(idx + 13).trim();
                    String numStr = after.replaceAll("[^0-9].*", "");
                    long downloads = Long.parseLong(numStr);
                    return Map.of("package", packageName, "monthly_downloads", downloads);
                }
                return Map.of("package", packageName, "data", body.substring(0, Math.min(200, body.length())));
            } catch (Exception e) {
                return Map.of("package", packageName, "error", e.getMessage());
            }
        }

        @Tool(name = "fetch_npm_downloads", description = "Fetch monthly download stats for an NPM package")
        public Map<String, Object> fetchNpmDownloads(String packageName) {
            try {
                String url = "https://api.npmjs.org/downloads/point/last-month/" + packageName;
                String body = get(url);
                int idx = body.indexOf("\"downloads\":");
                if (idx >= 0) {
                    String after = body.substring(idx + 12).trim();
                    String numStr = after.replaceAll("[^0-9].*", "");
                    long downloads = Long.parseLong(numStr);
                    return Map.of("package", packageName, "monthly_downloads", downloads);
                }
                return Map.of("package", packageName, "data", body.substring(0, Math.min(200, body.length())));
            } catch (Exception e) {
                return Map.of("package", packageName, "error", e.getMessage());
            }
        }

        @Tool(name = "compare_numbers", description = "Compare two numeric values and compute ratio")
        public Map<String, Object> compareNumbers(String labelA, double valueA, String labelB, double valueB, String metric) {
            double ratio = valueB > 0 ? valueA / valueB : 0;
            String leader = valueA > valueB ? labelA : labelB;
            return Map.of(
                "metric", metric,
                labelA, valueA,
                labelB, valueB,
                "ratio", String.format("%.2f", ratio),
                "leader", leader
            );
        }
    }

    private static String get(String url) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(10))
            .header("User-Agent", "agentspan-java-example/1.0")
            .GET()
            .build();
        return HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    private static int countOccurrences(String text, String pattern) {
        int count = 0;
        int idx = 0;
        while ((idx = text.indexOf(pattern, idx)) >= 0) {
            count++;
            idx += pattern.length();
        }
        return count;
    }

    public static void main(String[] args) {
        List<ToolDef> researcherTools = ToolRegistry.fromInstance(new ResearcherTools());
        List<ToolDef> analystTools = ToolRegistry.fromInstance(new AnalystTools());

        Agent researcher = Agent.builder()
            .name("hn_researcher")
            .model(Settings.LLM_MODEL)
            .tools(researcherTools)
            .instructions(
                "You are a research agent. Search HackerNews for both 'Python programming' "
                + "and 'Rust programming'. Report the number of stories found for each.")
            .build();

        Agent analyst = Agent.builder()
            .name("hn_analyst")
            .model(Settings.LLM_MODEL)
            .tools(analystTools)
            .instructions(
                "You are a technology trend analyst. You receive research data about Python and Rust. "
                + "Fetch download stats: fetch_pypi_downloads('pip') for Python ecosystem, "
                + "fetch_npm_downloads('typescript') for comparison, then compare the numbers. "
                + "Write a brief analysis.")
            .build();

        Agent summarizer = Agent.builder()
            .name("trend_summarizer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a tech report writer. Summarize the research and analysis into a "
                + "concise, data-driven verdict: which language (Python vs Rust) shows "
                + "stronger developer momentum?")
            .build();

        // Pipeline: research → analyze → summarize
        Agent pipeline = Agent.builder()
            .name("tech_trend_pipeline")
            .model(Settings.LLM_MODEL)
            .instructions("Run the full tech trend analysis pipeline.")
            .agents(researcher, analyst, summarizer)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Compare Python and Rust: which has stronger developer mindshare?");
        result.printResult();

        Agentspan.shutdown();
    }
}
