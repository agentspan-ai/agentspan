// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.examples.Settings;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 00 — Hello World using the native Google ADK Java SDK.
 *
 * <p>Defines a real {@link LlmAgent} with {@code com.google.adk.agents.LlmAgent.builder()},
 * then hands it to {@link AdkBridge#toAgentspan} so it runs on the
 * Agentspan durable runtime.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>OpenAI/Gemini key configured in server credentials</li>
 * </ul>
 */
public class Example00HelloWorld {
    public static void main(String[] args) {
        LlmAgent adkAgent = LlmAgent.builder()
                .name("greeter")
                .model(Settings.LLM_MODEL)
                .instruction("You are a friendly greeter. Reply with a warm hello and one fun fact.")
                .build();

        Agent agent = AdkBridge.toAgentspan(adkAgent);

        AgentResult result = Agentspan.run(agent, "Say hello!");
        result.printResult();

        Agentspan.shutdown();
    }
}
