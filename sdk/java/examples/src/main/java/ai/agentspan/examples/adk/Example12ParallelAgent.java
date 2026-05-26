// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.agents.ParallelAgent;

/**
 * Example Adk 12 — Parallel Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/12_parallel_agent.py</code>.
 *
 * <p>Demonstrates: native ADK {@link ParallelAgent} runs sub-agents
 * concurrently — market / tech / risk analysts dispatched in parallel.
 * The bridge emits {@code _type: ParallelAgent} so the server compiles
 * this as a Conductor fan-out workflow.
 */
public class Example12ParallelAgent {

    public static void main(String[] args) {
        LlmAgent marketAnalyst = LlmAgent.builder()
            .name("market_analyst")
            .description("Provides a brief market analysis focused on trends and competition.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a market analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence market analysis. Focus on trends and competition.")
            .build();

        LlmAgent techAnalyst = LlmAgent.builder()
            .name("tech_analyst")
            .description("Provides a brief technical evaluation focused on innovation and capabilities.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a technology analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence technical evaluation. Focus on innovation and capabilities.")
            .build();

        LlmAgent riskAnalyst = LlmAgent.builder()
            .name("risk_analyst")
            .description("Provides a brief risk assessment focused on potential challenges.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a risk analyst. Given the company or product topic, "
                + "provide a brief 2-3 sentence risk assessment. Focus on potential challenges.")
            .build();

        // All three analysts dispatched concurrently by native ParallelAgent.
        ParallelAgent parallelAnalysis = ParallelAgent.builder()
            .name("parallel_analysis")
            .description("Fan-out to three analysts running in parallel.")
            .subAgents(marketAnalyst, techAnalyst, riskAnalyst)
            .build();

        AgentResult result = Agentspan.run(parallelAnalysis, "Analyze Tesla's electric vehicle business");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
