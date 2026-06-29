// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples.adk;

import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.examples.Settings;
import org.conductoross.conductor.ai.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 00 — Hello World using the native Google ADK Java SDK.
 *
 * <p>Defines a real {@link LlmAgent} with {@code com.google.adk.agents.LlmAgent.builder()},
 * and hands it directly to {@link org.conductoross.conductor.ai.Agentspan#run(Object, String)}
 * for execution on the durable Agentspan runtime.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>OpenAI/Gemini key configured in server credentials</li>
 * </ul>
 */
public class Example00HelloWorld {
    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        LlmAgent greeter = LlmAgent.builder()
                .name("greeter")
                .description("A friendly greeter that says hello and shares a fun fact.")
                .model(Settings.LLM_MODEL)
                .instruction("You are a friendly greeter. Reply with a warm hello and one fun fact.")
                .build();

        AgentResult result = runtime.run(greeter, "Say hello!");
        result.printResult();

        runtime.shutdown();
    }
}
