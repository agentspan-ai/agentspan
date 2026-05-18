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

import java.util.Map;

/**
 * Example Adk 23 — Callbacks (lifecycle hooks)
 *
 * <p>Java port of <code>sdk/python/examples/adk/23_callbacks.py</code>.
 *
 * <p>Demonstrates: lifecycle hooks (before/after_model_callback) registered
 * as Conductor worker tasks. The Java {@link GoogleADKAgent} builder does
 * not expose model callback wiring directly, so we expose the callback
 * payloads as regular tools that mirror the Python signatures, then
 * document the intent in the agent instructions.
 */
public class Example23Callbacks {

    static class Callbacks {

        @Tool(name = "log_before_model", value = "Called before each LLM invocation. Returns empty dict to continue normally.")
        public Map<String, Object> logBeforeModel(
                @P("callback_position") String callbackPosition,
                @P("agent_name") String agentName) {
            System.out.println("[CALLBACK] Before model call for agent '" + agentName + "'");
            return Map.of();
        }

        @Tool(name = "inspect_after_model", value = "Called after each LLM invocation. Inspects the response.")
        public Map<String, Object> inspectAfterModel(
                @P("callback_position") String callbackPosition,
                @P("agent_name") String agentName,
                @P("llm_result") String llmResult) {
            int wordCount = (llmResult == null || llmResult.isEmpty()) ? 0 : llmResult.split("\\s+").length;
            System.out.println("[CALLBACK] After model call for '" + agentName + "': " + wordCount + " words generated");
            if (wordCount > 500) {
                System.out.println("[CALLBACK] Warning: Response exceeds 500 words (" + wordCount + ")");
            }
            return Map.of();
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("monitored_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a helpful assistant. Answer questions concisely. "
                + "Keep responses under 200 words.")
            .tools(new Callbacks())
            .build();

        AgentResult result = Agentspan.run(agent,
            "Explain the difference between supervised and unsupervised machine learning.");
        result.printResult();

        Agentspan.shutdown();
    }
}
