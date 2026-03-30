// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 13 — Hierarchical Agents (nested agent teams)
 *
 * <p>Demonstrates multi-level agent hierarchies where a top-level orchestrator
 * delegates to team leads, who in turn delegate to specialists.
 *
 * <pre>
 * CEO Agent
 * ├── Engineering Lead (HANDOFF)
 * │   ├── Backend Developer
 * │   └── Frontend Developer
 * └── Marketing Lead (HANDOFF)
 *     ├── Content Writer
 *     └── SEO Specialist
 * </pre>
 */
public class Example13HierarchicalAgents {

    public static void main(String[] args) {
        // ── Level 3: Individual specialists ─────────────────────────────

        Agent backendDev = Agent.builder()
            .name("backend_dev")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a backend developer. Design APIs, databases, and server architecture. "
                + "Provide technical recommendations with brief code examples.")
            .build();

        Agent frontendDev = Agent.builder()
            .name("frontend_dev")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a frontend developer. Design UI components and client-side architecture. "
                + "Provide recommendations with brief code examples.")
            .build();

        Agent contentWriter = Agent.builder()
            .name("content_writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a content writer. Create blog posts, landing page copy, and marketing materials. "
                + "Write engaging, clear content.")
            .build();

        Agent seoSpecialist = Agent.builder()
            .name("seo_specialist")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an SEO specialist. Optimize content for search engines, "
                + "suggest keywords, and improve page rankings.")
            .build();

        // ── Level 2: Team leads ──────────────────────────────────────────

        Agent engineeringLead = Agent.builder()
            .name("engineering_lead")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the engineering lead. Route technical questions to the right specialist: "
                + "backend_dev for APIs/databases/servers, "
                + "frontend_dev for UI/UX/client-side.")
            .agents(backendDev, frontendDev)
            .strategy(Strategy.HANDOFF)
            .build();

        Agent marketingLead = Agent.builder()
            .name("marketing_lead")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the marketing lead. Route marketing questions to the right specialist: "
                + "content_writer for blog posts/copy, "
                + "seo_specialist for SEO/keywords/rankings.")
            .agents(contentWriter, seoSpecialist)
            .strategy(Strategy.HANDOFF)
            .build();

        // ── Level 1: CEO orchestrator ────────────────────────────────────

        Agent ceo = Agent.builder()
            .name("ceo")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the CEO. Route requests to the right department: "
                + "engineering_lead for technical/development questions, "
                + "marketing_lead for marketing/content/SEO questions.")
            .agents(engineeringLead, marketingLead)
            .strategy(Strategy.HANDOFF)
            .build();

        // Run: technical question → CEO → Engineering Lead → Backend Dev
        System.out.println("=== Technical Question → Engineering → Backend ===");
        AgentResult result = Agentspan.run(ceo,
            "Design a REST API for a user authentication system with JWT tokens");
        result.printResult();

        Agentspan.shutdown();
    }
}
