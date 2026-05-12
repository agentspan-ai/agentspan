// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 00 — Hello World
 *
 * <p>Java port of <code>sdk/python/examples/adk/00_hello_world.py</code>.
 *
 * <p>Demonstrates: minimal Google ADK greeting agent — no tools, no structured
 * output, one turn. The simplest possible ADK agent.
 */
public class ExampleAdk00HelloWorld {
    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("greeter")
            .model(Settings.LLM_MODEL)
            .instruction("You are a friendly greeter. Reply with a warm hello and one fun fact.")
            .build();

        AgentResult result = Agentspan.run(agent, "Say hello!");
        result.printResult();

        Agentspan.shutdown();
    }
}
