// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.genai.types.GenerateContentConfig;

/**
 * Example Adk 05 — Generation Config
 *
 * <p>Java port of <code>sdk/python/examples/adk/05_generation_config.py</code>.
 *
 * <p>Demonstrates: temperature and output control via native ADK's
 * {@code generateContentConfig(...)}.
 */
public class Example05GenerationConfig {
    public static void main(String[] args) {
        // Precise agent — low temperature for factual responses
        LlmAgent factualAgent = LlmAgent.builder()
            .name("fact_checker")
            .description("A low-temperature fact-checker that gives precise, well-sourced answers.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a precise fact-checker. Provide accurate, well-sourced "
                + "answers. Be concise and avoid speculation.")
            .generateContentConfig(GenerateContentConfig.builder()
                .temperature(0.1f)
                .build())
            .build();

        // Creative agent — high temperature for creative writing
        LlmAgent creativeAgent = LlmAgent.builder()
            .name("storyteller")
            .description("A high-temperature storyteller that produces vivid, imaginative narratives.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an imaginative storyteller. Create vivid, engaging "
                + "narratives with rich descriptions and unexpected twists.")
            .generateContentConfig(GenerateContentConfig.builder()
                .temperature(0.9f)
                .build())
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
