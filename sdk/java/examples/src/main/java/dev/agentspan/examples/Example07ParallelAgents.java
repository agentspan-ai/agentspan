// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 07 — Parallel Agents
 *
 * <p>Demonstrates running multiple agents in parallel. All sub-agents receive
 * the same prompt and run concurrently. Results are aggregated.
 */
public class Example07ParallelAgents {

    public static void main(String[] args) {
        // Analysts running in parallel
        Agent technicalAnalyst = Agent.builder()
            .name("technical_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technical analyst. Analyze the topic from a technical perspective. "
                + "Focus on implementation details, technical challenges, and engineering aspects. "
                + "Be specific and technical.")
            .build();

        Agent businessAnalyst = Agent.builder()
            .name("business_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a business analyst. Analyze the topic from a business perspective. "
                + "Focus on market opportunities, ROI, competitive landscape, and business impact. "
                + "Use business terminology.")
            .build();

        Agent riskAnalyst = Agent.builder()
            .name("risk_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a risk analyst. Analyze the topic from a risk management perspective. "
                + "Identify potential risks, mitigation strategies, and regulatory considerations. "
                + "Use a risk framework.")
            .build();

        // Run all analysts in parallel
        Agent analysisTeam = Agent.builder()
            .name("analysis_team")
            .model(Settings.LLM_MODEL)
            .agents(technicalAnalyst, businessAnalyst, riskAnalyst)
            .strategy(Strategy.PARALLEL)
            .build();

        AgentResult result = Agentspan.run(analysisTeam,
            "Analyze the adoption of AI in healthcare for patient diagnosis");
        result.printResult();

        Agentspan.shutdown();
    }
}
