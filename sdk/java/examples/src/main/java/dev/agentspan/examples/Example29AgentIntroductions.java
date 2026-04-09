// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 29 — Agent Introductions
 *
 * <p>Demonstrates the {@code introduction} parameter which adds a self-introduction
 * to the conversation transcript at the start of multi-agent group chats
 * (ROUND_ROBIN, RANDOM, SWARM, MANUAL).
 *
 * <p>This helps agents understand who they're collaborating with and establishes
 * context for the discussion before the first turn.
 */
public class Example29AgentIntroductions {

    public static void main(String[] args) {
        // ── Agents with introductions ──────────────────────────────────────

        Agent architect = Agent.builder()
            .name("architect")
            .model(Settings.LLM_MODEL)
            .introduction(
                "I am the Software Architect. I focus on system design, scalability, "
                + "and technical trade-offs. I'll evaluate proposals from an architecture "
                + "perspective.")
            .instructions(
                "You are a software architect. Focus on system design, scalability, "
                + "and architectural patterns. Keep responses to 2-3 paragraphs.")
            .build();

        Agent securityEngineer = Agent.builder()
            .name("security_engineer")
            .model(Settings.LLM_MODEL)
            .introduction(
                "I am the Security Engineer. I focus on threat modeling, authentication, "
                + "authorization, and data protection. I'll flag any security concerns.")
            .instructions(
                "You are a security engineer. Focus on security implications, "
                + "vulnerabilities, and best practices. Keep responses to 2-3 paragraphs.")
            .build();

        Agent productManager = Agent.builder()
            .name("product_manager")
            .model(Settings.LLM_MODEL)
            .introduction(
                "I am the Product Manager. I focus on user needs, business value, "
                + "and delivery timelines. I'll ensure we stay focused on what matters "
                + "to customers.")
            .instructions(
                "You are a product manager. Focus on user needs, business value, "
                + "and prioritization. Keep responses to 2-3 paragraphs.")
            .build();

        // ── Team discussion with introductions ─────────────────────────────
        // Introductions are automatically prepended to the conversation so
        // each agent knows who's in the room.

        Agent designReview = Agent.builder()
            .name("design_review")
            .model(Settings.LLM_MODEL)
            .agents(architect, securityEngineer, productManager)
            .strategy(Strategy.ROUND_ROBIN)
            .maxTurns(6)
            .build();

        AgentResult result = Agentspan.run(designReview,
            "Review the design for a new user authentication system that uses "
            + "passkeys (WebAuthn) instead of passwords.");
        result.printResult();

        Agentspan.shutdown();
    }
}
