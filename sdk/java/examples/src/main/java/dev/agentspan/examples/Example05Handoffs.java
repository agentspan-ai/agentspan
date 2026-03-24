// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 05 — Multi-Agent Handoffs
 *
 * <p>Demonstrates multi-agent orchestration with handoff strategy.
 * The orchestrator LLM decides which specialist sub-agent to invoke.
 */
public class Example05Handoffs {

    public static void main(String[] args) {
        // Specialist agents
        Agent techSupport = Agent.builder()
            .name("tech_support")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technical support specialist. Help users troubleshoot technical issues "
                + "with software, hardware, and connectivity problems. "
                + "Provide clear step-by-step solutions.")
            .build();

        Agent billingSupport = Agent.builder()
            .name("billing_support")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a billing support specialist. Help users with payment issues, "
                + "subscription questions, refunds, and billing discrepancies. "
                + "Be professional and empathetic.")
            .build();

        Agent generalSupport = Agent.builder()
            .name("general_support")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a general customer support agent. Handle general inquiries, "
                + "product information requests, and questions that don't fit tech or billing.")
            .build();

        // Orchestrator with handoff strategy
        Agent supportOrchestrator = Agent.builder()
            .name("support_orchestrator")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a customer support orchestrator. Route customer inquiries to the right specialist:\n"
                + "- 'tech_support' for technical issues\n"
                + "- 'billing_support' for payment and billing issues\n"
                + "- 'general_support' for other inquiries\n"
                + "Analyze the customer's message and hand off to the appropriate agent.")
            .agents(techSupport, billingSupport, generalSupport)
            .strategy(Strategy.HANDOFF)
            .build();

        // Test with a technical issue
        System.out.println("=== Technical Issue ===");
        AgentResult techResult = Agentspan.run(supportOrchestrator,
            "My software keeps crashing when I try to export files. Error code: 0x80004005");
        techResult.printResult();

        Agentspan.shutdown();
    }
}
