// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 01 — Basic Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/01_basic_agent.py</code>.
 *
 * <p>Demonstrates: the simplest Google ADK agent — defined via the
 * native {@link LlmAgent} builder and bridged to the Agentspan durable
 * runtime via {@link ai.agentspan.Agentspan#run(Object, String)}.
 */
public class Example01BasicAgent {
    public static void main(String[] args) {
        LlmAgent researcher = LlmAgent.builder()
            .name("greeter")
            .description("A friendly assistant that gives concise, helpful answers.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a friendly assistant. Keep your responses concise and helpful.")
            .build();

        AgentResult result = Agentspan.run(researcher,
            "Say hello and tell me a fun fact about machine learning.");
        System.out.println("researcher completed with status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
