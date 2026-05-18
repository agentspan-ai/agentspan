// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.Strategy;
import ai.agentspan.handoff.OnTextMention;
import ai.agentspan.model.AgentResult;

/**
 * Example 17 — Swarm Orchestration (LLM-driven agent transitions)
 *
 * <p>Demonstrates {@code Strategy.SWARM} where each agent gets transfer tools
 * and the LLM decides when to hand off by calling the appropriate transfer tool.
 *
 * <p>Flow:
 * <ol>
 *   <li>Front-line support agent triages the request</li>
 *   <li>LLM calls transfer_to_refund_specialist or transfer_to_tech_support</li>
 *   <li>The specialist handles the request and provides a final response</li>
 * </ol>
 */
public class Example17SwarmOrchestration {

    public static void main(String[] args) {
        // ── Specialist agents ────────────────────────────────────────────

        Agent refundAgent = Agent.builder()
            .name("refund_specialist")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a refund specialist. Process the customer's refund request. "
                + "Check eligibility, confirm the refund amount, and let them know the timeline. "
                + "Be empathetic and clear.")
            .build();

        Agent techAgent = Agent.builder()
            .name("tech_support")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technical support specialist. Diagnose the customer's "
                + "technical issue and provide clear troubleshooting steps.")
            .build();

        // ── Front-line support with SWARM strategy ───────────────────────

        Agent support = Agent.builder()
            .name("support")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the front-line customer support agent. Triage customer requests. "
                + "If the customer needs a refund, transfer to the refund specialist. "
                + "If they have a technical issue, transfer to tech support. "
                + "Use the transfer tools available to you.")
            .agents(refundAgent, techAgent)
            .strategy(Strategy.SWARM)
            .handoffs(
                OnTextMention.of("refund", "refund_specialist"),
                OnTextMention.of("technical", "tech_support")
            )
            .maxTurns(3)
            .build();

        // ── Run test scenarios ───────────────────────────────────────────

        System.out.println("=== Refund Scenario ===");
        AgentResult refundResult = Agentspan.run(support,
            "I bought a product last week and it arrived damaged. I want my money back.");
        refundResult.printResult();

        System.out.println("\n=== Technical Issue Scenario ===");
        AgentResult techResult = Agentspan.run(support,
            "My app keeps crashing whenever I try to upload a file larger than 10MB.");
        techResult.printResult();

        Agentspan.shutdown();
    }
}
