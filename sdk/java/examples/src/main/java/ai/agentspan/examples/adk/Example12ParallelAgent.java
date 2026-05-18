// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 12 — Parallel Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/12_parallel_agent.py</code>.
 *
 * <p>Demonstrates: Python's {@code ParallelAgent} runs sub-agents concurrently
 * and aggregates results. The Java {@link GoogleADKAgent} models the same
 * intent through a coordinator delegating to multiple analysts in parallel.
 */
public class Example12ParallelAgent {

    public static void main(String[] args) {
        Agent marketAnalyst = GoogleADKAgent.builder()
            .name("market_analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a market analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence market analysis. Focus on trends and competition.")
            .build();

        Agent techAnalyst = GoogleADKAgent.builder()
            .name("tech_analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a technology analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence technical evaluation. Focus on innovation and capabilities.")
            .build();

        Agent riskAnalyst = GoogleADKAgent.builder()
            .name("risk_analyst")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a risk analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence risk assessment. Focus on potential challenges.")
            .build();

        // All three should run in parallel; aggregation happens at the orchestrator
        Agent parallelAnalysis = GoogleADKAgent.builder()
            .name("parallel_analysis")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate three parallel analysts: market_analyst, tech_analyst, "
                + "and risk_analyst. Dispatch the user's topic to all three concurrently, "
                + "then aggregate their findings into a combined report.")
            .subAgents(marketAnalyst, techAnalyst, riskAnalyst)
            .build();

        AgentResult result = Agentspan.run(parallelAnalysis, "Analyze Tesla's electric vehicle business");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
