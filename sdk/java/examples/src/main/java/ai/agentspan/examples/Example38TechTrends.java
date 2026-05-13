// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example 38 — Tech Trend Analyzer (multi-agent research pipeline)
 *
 * <p>Compares two programming languages using real data from HackerNews,
 * Wikipedia, PyPI, and NPM.
 *
 * <pre>
 * researcher → analyst → pdf_generator
 * </pre>
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
                int limit = Math.max(1, Math.min(maxResults > 0 ? maxResults : 8, 20));
                String url = "https://hn.algolia.com/api/v1/search?query=" + encoded
                    + "&tags=story&hitsPerPage=" + limit;
                String body = get(url);
                int hitCount = countOccurrences(body, "\"objectID\"");
                String snippet = body.length() > 500 ? body.substring(0, 500) + "..." : body;
                return Map.of("query", query, "stories_found", hitCount, "data_preview", snippet);
            } catch (Exception e) {
                return Map.of("query", query, "error", e.getMessage(), "stories_found", 0);
            }
        }

        @Tool(name = "get_hn_story_comments", description = "Fetch comments for a HackerNews story by ID")
        public Map<String, Object> getHnStoryComments(String storyId) {
            try {
                String url = "https://hacker-news.firebaseio.com/v0/item/" + storyId + ".json";
                String body = get(url);
                int idx = body.indexOf("\"title\":");
                String title = idx >= 0 ? body.substring(idx + 9, Math.min(idx + 80, body.length())).replaceAll("\".*", "") : "Unknown";
                return Map.of("story_id", storyId, "title", title, "data_preview",
                    body.substring(0, Math.min(300, body.length())));
            } catch (Exception e) {
                return Map.of("story_id", storyId, "error", e.getMessage());
            }
        }

        @Tool(name = "get_wikipedia_summary", description = "Fetch the Wikipedia introduction paragraph for a technology or topic")
        public Map<String, Object> getWikipediaSummary(String topic) {
            try {
                String encoded = URLEncoder.encode(topic, StandardCharsets.UTF_8);
                String url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + encoded;
                String body = get(url);
                int idx = body.indexOf("\"extract\":");
                String extract = idx >= 0
                    ? body.substring(idx + 11, Math.min(idx + 400, body.length())).replaceAll("\".*", "")
                    : "";
                return Map.of("topic", topic, "extract", extract);
            } catch (Exception e) {
                return Map.of("topic", topic, "error", e.getMessage());
            }
        }
    }

    static class AnalystTools {
        @Tool(name = "fetch_pypi_downloads", description = "Fetch monthly download stats for a PyPI package")
        public Map<String, Object> fetchPypiDownloads(String packageName) {
            try {
                String url = "https://pypistats.org/api/packages/" + packageName + "/recent";
                String body = get(url);
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
                "metric", metric, labelA, valueA, labelB, valueB,
                "ratio", String.format("%.2f", ratio), "leader", leader
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
        int count = 0, idx = 0;
        while ((idx = text.indexOf(pattern, idx)) >= 0) { count++; idx += pattern.length(); }
        return count;
    }

    /** Build a ToolDef matching Python SDK's pdf_tool() — uses Conductor's GENERATE_PDF task. */
    private static ToolDef pdfTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("markdown", Map.of("type", "string", "description", "Markdown text to convert to PDF."));
        props.put("pageSize", Map.of("type", "string", "description", "Page size: A4, LETTER, LEGAL, A3, or A5.", "default", "A4"));
        props.put("theme", Map.of("type", "string", "description", "Style preset: 'default' or 'compact'.", "default", "default"));
        props.put("baseFontSize", Map.of("type", "number", "description", "Base font size in points.", "default", 11));
        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("markdown"));
        return ToolDef.builder()
            .name("generate_pdf")
            .description("Generate a PDF document from markdown text.")
            .inputSchema(inputSchema)
            .toolType("generate_pdf")
            .config(Map.of("taskType", "GENERATE_PDF"))
            .build();
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) {
        List<ToolDef> rawResearcherTools = ToolRegistry.fromInstance(new ResearcherTools());
        List<ToolDef> rawAnalystTools = ToolRegistry.fromInstance(new AnalystTools());

        // Python's search_hackernews has max_results with a default — only query is required.
        // Find tools by name (getMethods() order is not guaranteed).
        ToolDef rawSearch = rawResearcherTools.stream()
            .filter(t -> "search_hackernews".equals(t.getName())).findFirst().get();
        Map<String, Object> searchSchema = new LinkedHashMap<>((Map<String, Object>) rawSearch.getInputSchema());
        searchSchema.put("required", List.of("query"));
        ToolDef searchTool = ToolDef.builder()
            .name(rawSearch.getName()).description(rawSearch.getDescription())
            .inputSchema(searchSchema).outputSchema(rawSearch.getOutputSchema())
            .toolType(rawSearch.getToolType()).func(rawSearch.getFunc())
            .build();

        // Build researcher tools in Python declaration order:
        // [search_hackernews, get_hn_story_comments, get_wikipedia_summary]
        ToolDef hnComments = rawResearcherTools.stream()
            .filter(t -> "get_hn_story_comments".equals(t.getName())).findFirst().get();
        ToolDef wikiSummary = rawResearcherTools.stream()
            .filter(t -> "get_wikipedia_summary".equals(t.getName())).findFirst().get();
        List<ToolDef> researcherTools = List.of(searchTool, hnComments, wikiSummary);

        // Build analyst tools in Python declaration order:
        // [fetch_pypi_downloads, fetch_npm_downloads, compare_numbers]
        ToolDef pypiDl = rawAnalystTools.stream()
            .filter(t -> "fetch_pypi_downloads".equals(t.getName())).findFirst().get();
        ToolDef npmDl = rawAnalystTools.stream()
            .filter(t -> "fetch_npm_downloads".equals(t.getName())).findFirst().get();
        ToolDef compareNums = rawAnalystTools.stream()
            .filter(t -> "compare_numbers".equals(t.getName())).findFirst().get();
        List<ToolDef> analystTools = List.of(pypiDl, npmDl, compareNums);

        Agent researcher = Agent.builder()
            .name("hn_researcher")
            .model(Settings.LLM_MODEL)
            .tools(researcherTools)
            .maxTokens(4000)
            .instructions(
                "You are a technology research assistant. You MUST call tools to gather real data. "
                + "Search HackerNews for Python and Rust stories, fetch comments, and get Wikipedia summaries.")
            .build();

        Agent analyst = Agent.builder()
            .name("hn_analyst")
            .model(Settings.LLM_MODEL)
            .tools(analystTools)
            .maxTokens(4000)
            .instructions(
                "You are a technology trend analyst. Fetch download stats for Python and Rust "
                + "ecosystems and compare the numbers. Write a final markdown report.")
            .build();

        Agent pdfGenerator = Agent.builder()
            .name("pdf_report_generator")
            .model(Settings.LLM_MODEL)
            .tools(List.of(pdfTool()))
            .maxTokens(4000)
            .instructions(
                "You receive a markdown report. Your ONLY job is to call the generate_pdf "
                + "tool with the full markdown content to produce a PDF document. "
                + "Pass the entire report as the 'markdown' parameter. "
                + "Do not modify or summarize the content — pass it through as-is.")
            .build();

        // Pipeline: research → analyze → generate PDF
        Agent pipeline = Agent.builder()
            .name("tech_trend_pipeline")
            .model(Settings.LLM_MODEL)
            .agents(researcher, analyst, pdfGenerator)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Compare Python and Rust: which has stronger developer mindshare?");
        result.printResult();

        Agentspan.shutdown();
    }
}
