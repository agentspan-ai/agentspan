// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example OpenAi 10 — Multi-Model Handoff
 *
 * <p>Java port of <code>sdk/python/examples/openai/10_multi_model.py</code>.
 *
 * <p>Demonstrates: a cheap-and-fast triage agent (primary model) that hands
 * off to two specialists running on a more capable secondary model — a
 * documentation specialist with a doc-search tool and a code specialist
 * with a code-generation tool.
 *
 * <p>Python parity gap: the Python original attaches {@code ModelSettings}
 * (temperature / max_tokens) to each agent. The current {@link OpenAIAgent}
 * builder does not surface model_settings, so we set the model and tools
 * only. The intended settings from the Python original are:
 * <ul>
 *   <li>{@code triage}: {@code temperature=0.1}.</li>
 *   <li>{@code doc_specialist}: {@code temperature=0.2, max_tokens=500}.</li>
 *   <li>{@code code_specialist}: {@code temperature=0.3, max_tokens=800}.</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 *   <li>AGENT_SECONDARY_LLM_MODEL=openai/gpt-4o</li>
 * </ul>
 */
public class Example10MultiModel {

    static class DocTools {
        @Tool(name = "search_docs", description = "Search the documentation for relevant information.")
        public String searchDocs(String query) {
            Map<String, String> docs = new LinkedHashMap<>();
            docs.put("authentication", "Use OAuth 2.0 with JWT tokens. See /auth/login endpoint.");
            docs.put("rate limiting", "100 requests/minute per API key. 429 status on exceeded.");
            docs.put("pagination", "Use cursor-based pagination with ?cursor=xxx&limit=50.");
            docs.put("webhooks", "POST to /webhooks/register with event types and callback URL.");

            String q = query.toLowerCase();
            for (Map.Entry<String, String> e : docs.entrySet()) {
                if (q.contains(e.getKey())) return e.getValue();
            }
            return "No documentation found. Try rephrasing your query.";
        }
    }

    static class CodeTools {
        @Tool(name = "generate_code_sample", description = "Generate a code sample for a given topic.")
        public String generateCodeSample(String language, String topic) {
            String key = language.toLowerCase() + "|" + topic.toLowerCase();
            switch (key) {
                case "python|authentication":
                    return "import requests\n"
                            + "resp = requests.post('/auth/login', json={'key': 'API_KEY'})\n"
                            + "token = resp.json()['token']";
                case "javascript|authentication":
                    return "const resp = await fetch('/auth/login', {\n"
                            + "  method: 'POST',\n"
                            + "  body: JSON.stringify({ key: 'API_KEY' })\n"
                            + "});\n"
                            + "const { token } = await resp.json();";
                default:
                    return "// Sample for " + topic + " in " + language + "\n"
                            + "// (template not available)";
            }
        }
    }

    public static void main(String[] args) {
        // Knowledgeable model for doc lookups (secondary model).
        Agent docSpecialist = OpenAIAgent.builder()
                .name("doc_specialist")
                .instructions(
                        "You are a documentation specialist. Search the docs and provide "
                                + "clear, well-structured answers. Include relevant links and examples.")
                .model(Settings.SECONDARY_LLM_MODEL)
                .tools(new DocTools())
                .build();

        // Code-focused specialist (secondary model).
        Agent codeSpecialist = OpenAIAgent.builder()
                .name("code_specialist")
                .instructions(
                        "You are a code example specialist. Generate clean, well-commented "
                                + "code samples. Always specify the language and include error handling.")
                .model(Settings.SECONDARY_LLM_MODEL)
                .tools(new CodeTools())
                .build();

        // Fast, cheap model for initial triage with handoffs to specialists.
        Agent triage = OpenAIAgent.builder()
                .name("triage")
                .instructions(
                        "You are a documentation triage agent. Determine what the user needs "
                                + "and hand off to the appropriate specialist:\n"
                                + "- For documentation lookups -> doc_specialist\n"
                                + "- For code examples -> code_specialist\n"
                                + "Keep your response to one sentence before handing off.")
                .model(Settings.LLM_MODEL)
                .handoffs(docSpecialist, codeSpecialist)
                .build();

        AgentResult result = Agentspan.run(
                triage,
                "I need a Python code example for authenticating with the API.");
        result.printResult();

        Agentspan.shutdown();
    }
}
