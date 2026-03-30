// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 66 — Handoff to Parallel (delegate to a multi-agent group)
 *
 * <p>Demonstrates a parent agent that can hand off to either a single agent
 * (for quick checks) or a parallel multi-agent group (for deep analysis).
 * The parallel sub-agent runs its own fan-out/fan-in internally.
 *
 * <pre>
 * coordinator (HANDOFF)
 * ├── quick_check               (single agent, fast)
 * └── deep_analysis (PARALLEL)
 *     ├── market_analyst_66
 *     └── risk_analyst_66
 * </pre>
 */
public class Example66HandoffToParallel {

    public static void main(String[] args) {
        // ── Quick check (single agent) ─────────────────────────────────────

        Agent quickCheck = Agent.builder()
            .name("quick_check")
            .model(Settings.LLM_MODEL)
            .instructions("You provide quick, 1-sentence assessments. Be brief and direct.")
            .build();

        // ── Deep analysis (parallel group) ────────────────────────────────

        Agent deepAnalysis = Agent.builder()
            .name("deep_analysis")
            .model(Settings.LLM_MODEL)
            .instructions("Coordinate in-depth analysis across market and risk dimensions.")
            .agents(
                Agent.builder()
                    .name("market_analyst_66")
                    .model(Settings.LLM_MODEL)
                    .instructions(
                        "You are a market analyst. Analyze the market opportunity: "
                        + "size, growth rate, key players. 3-4 bullet points.")
                    .build(),
                Agent.builder()
                    .name("risk_analyst_66")
                    .model(Settings.LLM_MODEL)
                    .instructions(
                        "You are a risk analyst. Identify the top 3 risks: "
                        + "regulatory, technical, and competitive. 3-4 bullet points.")
                    .build()
            )
            .strategy(Strategy.PARALLEL)
            .build();

        // ── Coordinator with HANDOFF strategy ─────────────────────────────

        Agent coordinator = Agent.builder()
            .name("coordinator_66")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a business strategist. Route requests to the right team:\n"
                + "- quick_check for simple yes/no questions or quick assessments\n"
                + "- deep_analysis for comprehensive analysis requiring multiple perspectives")
            .agents(quickCheck, deepAnalysis)
            .strategy(Strategy.HANDOFF)
            .build();

        System.out.println("=== Scenario 1: Deep analysis (handoff → parallel group) ===");
        AgentResult r1 = Agentspan.run(coordinator,
            "Provide a deep analysis of entering the AI healthcare market.");
        r1.printResult();

        System.out.println("\n=== Scenario 2: Quick check (handoff → single agent) ===");
        AgentResult r2 = Agentspan.run(coordinator,
            "Is the mobile app market still growing?");
        r2.printResult();

        Agentspan.shutdown();
    }
}
