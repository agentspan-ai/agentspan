// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.GoogleSearchTool;

/**
 * Example Adk 36 — Built-in Tools (Google Search)
 *
 * <p>Demonstrates: native ADK ships ready-made tool instances like
 * {@link GoogleSearchTool} that the agent can use without any local
 * implementation. The bridge detects these subclasses of
 * {@code BaseTool} and emits the corresponding {@code _type} marker on
 * the wire; the server normalizer wires the built-in handler in the
 * compiled workflow.
 *
 * <p>Same pattern works for {@code BuiltInCodeExecutionTool} and
 * {@code McpToolset} (and any other {@code BaseToolset}, which the bridge
 * expands into its constituent tools via {@code getTools(null)}).
 */
public class Example36BuiltInTools {

    public static void main(String[] args) {
        LlmAgent toolUser = LlmAgent.builder()
                .name("research_assistant")
                .description("An assistant that can search the web with the built-in Google Search tool.")
                .model(Settings.LLM_MODEL)
                .instruction(
                        "You are a research assistant. When the user asks about a topic, "
                        + "use the google_search tool to find current information, then "
                        + "summarize the most relevant facts in 2-3 sentences.")
                .tools(new GoogleSearchTool())
                .build();

        AgentResult result = Agentspan.run(toolUser,
                "What are the most recent developments in fusion energy research?");
        result.printResult();

        Agentspan.shutdown();
    }
}
