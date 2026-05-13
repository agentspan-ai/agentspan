// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

/**
 * Example 01 — Basic Agent
 *
 * <p>Demonstrates the simplest possible agent: a single LLM with no tools.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o</li>
 * </ul>
 */
public class Example01BasicAgent {
    public static void main(String[] args) {
        Agent agent = Agent.builder()
            .name("basic_assistant")
            .model(Settings.LLM_MODEL)
            .instructions("You are a helpful assistant.")
            .build();

        AgentResult result = Agentspan.run(agent, "What is the capital of France?");
        result.printResult();

        Agentspan.shutdown();
    }
}
