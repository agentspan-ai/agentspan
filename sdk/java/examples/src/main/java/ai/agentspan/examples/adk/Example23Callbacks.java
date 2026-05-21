// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.Map;

/**
 * Example Adk 23 — Callbacks (lifecycle hooks)
 *
 * <p>Java port of <code>sdk/python/examples/adk/23_callbacks.py</code>.
 *
 * <p>Demonstrates: lifecycle hooks (before/after_model_callback) modeled as
 * function tools that surface the callback payloads. Native ADK exposes
 * {@code beforeModelCallback}/{@code afterModelCallback} on the builder but
 * the Agentspan {@link AdkBridge} currently only translates
 * {@link FunctionTool}s, so we keep the tool-based representation that
 * mirrors the Python signatures.
 */
public class Example23Callbacks {

    @Schema(description = "Called before each LLM invocation. Returns empty dict to continue normally.")
    public static Map<String, Object> logBeforeModel(
            @Schema(name = "callback_position", description = "Hook position") String callbackPosition,
            @Schema(name = "agent_name", description = "Name of the agent invoking the LLM") String agentName) {
        System.out.println("[CALLBACK] Before model call for agent '" + agentName + "'");
        return Map.of();
    }

    @Schema(description = "Called after each LLM invocation. Inspects the response.")
    public static Map<String, Object> inspectAfterModel(
            @Schema(name = "callback_position", description = "Hook position") String callbackPosition,
            @Schema(name = "agent_name", description = "Name of the agent invoking the LLM") String agentName,
            @Schema(name = "llm_result", description = "Raw LLM response text") String llmResult) {
        int wordCount = (llmResult == null || llmResult.isEmpty()) ? 0 : llmResult.split("\\s+").length;
        System.out.println("[CALLBACK] After model call for '" + agentName + "': " + wordCount + " words generated");
        if (wordCount > 500) {
            System.out.println("[CALLBACK] Warning: Response exceeds 500 words (" + wordCount + ")");
        }
        return Map.of();
    }

    public static void main(String[] args) {
        LlmAgent adk = LlmAgent.builder()
            .name("monitored_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a helpful assistant. Answer questions concisely. "
                + "Keep responses under 200 words.")
            .tools(
                FunctionTool.create(Example23Callbacks.class, "logBeforeModel"),
                FunctionTool.create(Example23Callbacks.class, "inspectAfterModel"))
            .build();

        Agent agent = AdkBridge.toAgentspan(adk);

        AgentResult result = Agentspan.run(agent,
            "Explain the difference between supervised and unsupervised machine learning.");
        result.printResult();

        Agentspan.shutdown();
    }
}
