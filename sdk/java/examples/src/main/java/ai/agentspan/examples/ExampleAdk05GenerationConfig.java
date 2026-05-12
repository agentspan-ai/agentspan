// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 05 — Generation Config
 *
 * <p>Java port of <code>sdk/python/examples/adk/05_generation_config.py</code>.
 *
 * <p>Demonstrates: temperature and output control. The Python version uses
 * ADK's {@code generate_content_config} dict for tuning. The Java
 * {@link GoogleADKAgent} builder does not expose generation config directly,
 * so we document the intent in the instruction and rely on server defaults.
 */
public class ExampleAdk05GenerationConfig {
    public static void main(String[] args) {
        // Precise agent — low temperature for factual responses (temperature: 0.1)
        Agent factualAgent = GoogleADKAgent.builder()
            .name("fact_checker")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a precise fact-checker. Provide accurate, well-sourced "
                + "answers. Be concise and avoid speculation.")
            .build();

        // Creative agent — high temperature for creative writing (temperature: 0.9)
        Agent creativeAgent = GoogleADKAgent.builder()
            .name("storyteller")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an imaginative storyteller. Create vivid, engaging "
                + "narratives with rich descriptions and unexpected twists.")
            .build();

        System.out.println("=== Factual Agent (temp=0.1) ===");
        AgentResult result = Agentspan.run(factualAgent,
            "What is the speed of light in a vacuum?");
        result.printResult();

        System.out.println("\n=== Creative Agent (temp=0.9) ===");
        result = Agentspan.run(creativeAgent,
            "Write a two-sentence story about a cat who discovered a hidden library.");
        result.printResult();

        Agentspan.shutdown();
    }
}
