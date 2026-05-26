// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 06 — Streaming
 *
 * <p>Java port of <code>sdk/python/examples/adk/06_streaming.py</code>.
 *
 * <p>Demonstrates: a documentation lookup ADK agent with a streaming-capable
 * pattern. The Python source shows {@code runtime.stream(...)} as an
 * alternative; this Java port uses the synchronous {@code Agentspan.run}.
 */
public class Example06Streaming {

    @Schema(description = "Search the product documentation.")
    public static Map<String, Object> searchDocumentation(
            @Schema(name = "query", description = "Search query") String query) {
        Map<String, Map<String, Object>> docs = new LinkedHashMap<>();
        docs.put("installation", Map.of(
            "title", "Installation Guide",
            "content", "Run `pip install mypackage`. Requires Python 3.9+."));
        docs.put("authentication", Map.of(
            "title", "Authentication",
            "content", "Use API keys via the X-API-Key header. Keys are managed in the dashboard."));
        docs.put("rate limits", Map.of(
            "title", "Rate Limiting",
            "content", "Free tier: 100 req/min. Pro: 1000 req/min. Enterprise: unlimited."));

        String q = query.toLowerCase();
        for (Map.Entry<String, Map<String, Object>> entry : docs.entrySet()) {
            if (q.contains(entry.getKey())) {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("found", true);
                r.putAll(entry.getValue());
                return r;
            }
        }
        return Map.of("found", false, "message", "No matching documentation found.");
    }

    public static void main(String[] args) {
        LlmAgent techWriter = LlmAgent.builder()
            .name("docs_assistant")
            .description("Looks up product documentation and answers user questions about it.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a documentation assistant. Use the search tool to find "
                + "relevant docs and provide clear, well-formatted answers.")
            .tools(FunctionTool.create(Example06Streaming.class, "searchDocumentation"))
            .build();

        AgentResult result = Agentspan.run(techWriter, "How do I authenticate with the API?");
        result.printResult();

        Agentspan.shutdown();
    }
}
