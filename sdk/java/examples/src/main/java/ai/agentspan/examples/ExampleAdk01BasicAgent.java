// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 01 — Basic Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/01_basic_agent.py</code>.
 *
 * <p>Demonstrates: the simplest Google ADK agent — defined via the
 * {@link GoogleADKAgent} builder and executed on the Conductor runtime.
 */
public class ExampleAdk01BasicAgent {
    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("greeter")
            .model(Settings.LLM_MODEL)
            .instruction("You are a friendly assistant. Keep your responses concise and helpful.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Say hello and tell me a fun fact about machine learning.");
        System.out.println("agent completed with status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
