// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
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
 * runtime via {@link AdkBridge}.
 */
public class Example01BasicAgent {
    public static void main(String[] args) {
        LlmAgent adk = LlmAgent.builder()
            .name("greeter")
            .model(Settings.LLM_MODEL)
            .instruction("You are a friendly assistant. Keep your responses concise and helpful.")
            .build();

        Agent agent = AdkBridge.toAgentspan(adk);

        AgentResult result = Agentspan.run(agent,
            "Say hello and tell me a fun fact about machine learning.");
        System.out.println("agent completed with status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
