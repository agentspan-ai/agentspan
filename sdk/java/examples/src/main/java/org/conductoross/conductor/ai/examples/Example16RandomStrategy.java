// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.enums.Strategy;
import org.conductoross.conductor.ai.model.AgentResult;

/**
 * Example 16 — Random Strategy (random agent selection each turn)
 *
 * <p>Demonstrates {@code Strategy.RANDOM} where a random sub-agent is
 * selected each iteration. Unlike round-robin (fixed rotation), random
 * selection adds variety — useful for brainstorming or diverse perspectives.
 *
 * <p>Three thinkers with different viewpoints each contribute until the
 * 6-turn budget is exhausted.
 */
public class Example16RandomStrategy {

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        Agent creative = Agent.builder()
            .name("creative")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a creative thinker. Suggest innovative, unconventional ideas. "
                + "Keep your response to 2-3 sentences.")
            .build();

        Agent practical = Agent.builder()
            .name("practical")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a practical thinker. Focus on feasibility and cost-effectiveness. "
                + "Keep your response to 2-3 sentences.")
            .build();

        Agent critical = Agent.builder()
            .name("critical")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a critical thinker. Identify risks and potential issues. "
                + "Keep your response to 2-3 sentences.")
            .build();

        // Random selection: each turn, one of the three agents is picked at random
        Agent brainstorm = Agent.builder()
            .name("brainstorm")
            .model(Settings.LLM_MODEL)
            .agents(creative, practical, critical)
            .strategy(Strategy.RANDOM)
            .maxTurns(6)
            .build();

        AgentResult result = runtime.run(brainstorm,
            "How should we approach building an AI-powered customer service platform?");
        result.printResult();

        runtime.shutdown();
    }
}
