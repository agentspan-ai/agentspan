// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example OpenAi 01 — Basic Agent
 *
 * <p>Java port of <code>sdk/python/examples/openai/01_basic_agent.py</code>.
 *
 * <p>Demonstrates: the simplest possible OpenAI Agents SDK agent — no tools,
 * just a name + instructions + model — wired through the Agentspan
 * {@link OpenAIAgent} factory so the server normalizes it into a Conductor
 * workflow.
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example01BasicAgent {

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("greeter")
                .instructions("You are a friendly assistant. Keep your responses concise and helpful.")
                .model(Settings.LLM_MODEL)
                .build();

        AgentResult result = Agentspan.run(
                agent,
                "Say hello and tell me a fun fact about the Python programming language.");
        result.printResult();

        Agentspan.shutdown();
    }
}
