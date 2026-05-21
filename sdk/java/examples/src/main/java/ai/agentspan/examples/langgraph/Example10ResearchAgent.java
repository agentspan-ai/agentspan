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

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Example LangGraph 10 — Multi-step research agent.
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/10_research_agent.py</code>
 * which combines search, summarize, and citation tools. The LangGraph4j
 * {@code AgentExecutor} walks the ReAct loop naturally as the LLM threads
 * results between the tools.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Search -> summarize -> cite multi-step tool chain</li>
 *   <li>Mock backing store so the example is deterministic and offline-friendly</li>
 *   <li>System prompt encoding the desired research procedure</li>
 * </ul>
 */
public class Example10ResearchAgent {

    static class ResearchTools {

        private static final Map<String, String[]> MOCK_SEARCH = new HashMap<>();
        static {
            MOCK_SEARCH.put("climate change", new String[] {
                    "Global temperatures have risen ~1.1 C since pre-industrial times (IPCC, 2023).",
                    "Sea levels are rising at 3.7 mm/year due to thermal expansion and ice melt.",
                    "Extreme weather events have increased in frequency and intensity since 1980."
            });
            MOCK_SEARCH.put("artificial intelligence", new String[] {
                    "Large language models have achieved human-level performance on many benchmarks.",
                    "The global AI market is projected to reach $1.8 trillion by 2030.",
                    "AI ethics and alignment remain active research challenges."
            });
            MOCK_SEARCH.put("renewable energy", new String[] {
                    "Solar PV costs have dropped 89% in the past decade.",
                    "Wind power capacity exceeded 900 GW globally in 2023.",
                    "Battery storage is the key bottleneck for 100% renewable grids."
            });
        }

        @Tool("Search for information on a topic. Returns a few bulleted facts.")
        public String search(@P("query") String query) {
            String q = query == null ? "" : query.toLowerCase(Locale.ROOT);
            for (Map.Entry<String, String[]> e : MOCK_SEARCH.entrySet()) {
                if (q.contains(e.getKey())) {
                    StringBuilder sb = new StringBuilder();
                    for (String f : e.getValue()) sb.append("- ").append(f).append("\n");
                    return sb.toString().trim();
                }
            }
            return "No specific results found for '" + query + "'. Try a broader search term.";
        }

        @Tool("Summarize the provided text into at most max_sentences sentences.")
        public String summarize(@P("text") String text, @P("max_sentences") int maxSentences) {
            if (text == null || text.isEmpty()) return "";
            String[] sentences = text.replace("\n", ". ").split("\\. ");
            int n = Math.min(maxSentences <= 0 ? 3 : maxSentences, sentences.length);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) {
                String s = sentences[i].trim();
                if (s.isEmpty()) continue;
                if (sb.length() > 0) sb.append(' ');
                sb.append(s);
                if (!s.endsWith(".")) sb.append('.');
            }
            return sb.toString();
        }

        @Tool("Generate a formatted citation for a given claim. "
                + "source_type is one of academic, news, report.")
        public String citeSource(@P("claim") String claim, @P("source_type") String sourceType) {
            String type = sourceType == null ? "academic" : sourceType.toLowerCase(Locale.ROOT);
            String citation;
            switch (type) {
                case "news":
                    citation = "Reuters. (2024, January 15). New developments in research. Reuters.com.";
                    break;
                case "report":
                    citation = "World Economic Forum. (2024). Global Report 2024. WEF Publications.";
                    break;
                default:
                    citation = "Smith, J., & Doe, A. (2024). Research findings on the topic. Journal of Science, 12(3), 45-67.";
            }
            String snippet = claim.length() > 80 ? claim.substring(0, 80) + "..." : claim;
            return "Claim: '" + snippet + "'\nCitation: " + citation;
        }
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        ResearchTools tools = new ResearchTools();
        AgentExecutor.Builder agent = AgentExecutor.builder().chatModel(model);
        agent.toolsFromObject(tools);

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
                agent,
                "You are a research assistant. For any research question: "
                + "1) call search for relevant information, "
                + "2) call summarize on the findings, "
                + "3) call cite_source for at least one key claim. "
                + "Be thorough and cite your sources.\n\n"
                + "What are the latest developments in climate change research? Include sources.",
                tools
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
