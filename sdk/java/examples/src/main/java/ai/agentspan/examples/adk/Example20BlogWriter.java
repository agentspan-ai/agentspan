// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 20 — Blog Writer
 *
 * <p>Java port of <code>sdk/python/examples/adk/20_blog_writer.py</code>.
 *
 * <p>Demonstrates: a sequential content pipeline of sub-agents
 * (researcher → writer → editor) with output_key state passing.
 */
public class Example20BlogWriter {

    static class ResearchTools {

        @Tool(name = "search_topic", value = "Search for information about a topic.")
        public Map<String, Object> searchTopic(@P("topic") String topic) {
            Map<String, Map<String, Object>> topics = new LinkedHashMap<>();
            topics.put("ai", Map.of(
                "key_points", List.of(
                    "AI adoption grew 72% in enterprises in 2024",
                    "Generative AI is transforming content creation and coding",
                    "AI safety and regulation are top policy priorities"
                ),
                "sources", List.of("TechReview", "AI Journal", "Industry Report 2024")
            ));
            topics.put("sustainability", Map.of(
                "key_points", List.of(
                    "Renewable energy hit 30% of global electricity in 2024",
                    "Carbon capture technology is scaling rapidly",
                    "Green bonds market exceeded $500B"
                ),
                "sources", List.of("GreenTech Weekly", "Climate Report", "Energy Journal")
            ));
            String t = topic.toLowerCase();
            for (Map.Entry<String, Map<String, Object>> entry : topics.entrySet()) {
                if (t.contains(entry.getKey())) {
                    Map<String, Object> r = new LinkedHashMap<>();
                    r.put("found", true);
                    r.putAll(entry.getValue());
                    return r;
                }
            }
            return Map.of(
                "found", true,
                "key_points", List.of("Key insight about " + topic),
                "sources", List.of("General Research")
            );
        }

        @Tool(name = "check_seo_keywords", value = "Get SEO keyword suggestions for a topic.")
        public Map<String, Object> checkSeoKeywords(@P("topic") String topic) {
            return Map.of(
                "primary_keyword", topic.toLowerCase().replace(" ", "-"),
                "related_keywords", List.of(topic + " trends", topic + " 2025", "best " + topic + " practices"),
                "search_volume", "high"
            );
        }
    }

    public static void main(String[] args) {
        Agent researcher = GoogleADKAgent.builder()
            .name("blog_researcher")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research assistant. Use the search tool to gather information "
                + "about the given topic. Present the key findings clearly.")
            .tools(new ResearchTools())
            .build();

        Agent writer = GoogleADKAgent.builder()
            .name("blog_writer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a blog writer. Based on the research notes provided, "
                + "write a short blog post (3-4 paragraphs). Include a catchy title. "
                + "Incorporate SEO keywords naturally.")
            .build();

        Agent editor = GoogleADKAgent.builder()
            .name("blog_editor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a blog editor. Review and polish the blog draft. "
                + "Improve clarity, flow, and engagement. Keep the same length. "
                + "Output only the final polished blog post.")
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("content_coordinator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a content coordinator. First use the researcher to gather information, "
                + "then the writer to create a draft, and finally the editor to polish it. "
                + "Present the final blog post to the user.")
            .subAgents(researcher, writer, editor)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Write a blog post about the conductor oss workflow and how its the best workflow engine for the agentic era."
            + "Make sure to write at-least 5000 word and use markdown to format the content");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
