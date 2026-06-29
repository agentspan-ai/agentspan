// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples.openai;

import org.conductoross.conductor.ai.examples.Settings;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.frameworks.OpenAIAgent;
import org.conductoross.conductor.ai.model.AgentResult;

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
        AgentRuntime runtime = new AgentRuntime();
        Agent agent = OpenAIAgent.builder()
                .name("greeter")
                .instructions("You are a friendly assistant. Keep your responses concise and helpful.")
                .model(Settings.LLM_MODEL)
                .build();

        AgentResult result = runtime.run(
                agent,
                "Say hello and tell me a fun fact about the Python programming language.");
        result.printResult();

        runtime.shutdown();
    }
}
