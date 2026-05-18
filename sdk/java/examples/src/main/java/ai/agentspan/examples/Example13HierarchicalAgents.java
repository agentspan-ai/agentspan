// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.Strategy;
import ai.agentspan.handoff.OnTextMention;
import ai.agentspan.model.AgentResult;

/**
 * Example 13 — Hierarchical Agents (nested agent teams)
 *
 * <p>Demonstrates multi-level agent hierarchies where a top-level orchestrator
 * delegates to team leads, who in turn delegate to specialists.
 *
 * <pre>
 * CEO Agent (SWARM)
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
                "You are a backend developer. You design APIs, databases, and server "
                + "architecture. Provide technical recommendations with code examples.")
            .build();

        Agent frontendDev = Agent.builder()
            .name("frontend_dev")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a frontend developer. You design UI components, user flows, "
                + "and client-side architecture. Provide recommendations with code examples.")
            .build();

        Agent contentWriter = Agent.builder()
            .name("content_writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a content writer. You create blog posts, landing page copy, "
                + "and marketing materials. Write engaging, clear content.")
            .build();

        Agent seoSpecialist = Agent.builder()
            .name("seo_specialist")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an SEO specialist. You optimize content for search engines, "
                + "suggest keywords, and improve page rankings.")
            .build();

        // ── Level 2: Team leads (handoff to specialists) ─────────────────

        Agent engineeringLead = Agent.builder()
            .name("engineering_lead")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the engineering lead. Route technical questions to the right "
                + "specialist: backend_dev for APIs/databases/servers, "
                + "frontend_dev for UI/UX/client-side.")
            .agents(backendDev, frontendDev)
            .strategy(Strategy.HANDOFF)
            .build();

        Agent marketingLead = Agent.builder()
            .name("marketing_lead")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the marketing lead. Route marketing questions to the right "
                + "specialist: content_writer for blog posts/copy, "
                + "seo_specialist for SEO/keywords/rankings.")
            .agents(contentWriter, seoSpecialist)
            .strategy(Strategy.HANDOFF)
            .build();

        // ── Level 1: CEO orchestrator (SWARM with condition-based handoffs) ──

        Agent ceo = Agent.builder()
            .name("ceo")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the CEO. Route requests to the right department: "
                + "engineering_lead for technical/development questions, "
                + "marketing_lead for marketing/content/SEO questions.")
            .agents(engineeringLead, marketingLead)
            .handoffs(
                OnTextMention.of("engineering_lead", "engineering_lead"),
                OnTextMention.of("marketing_lead", "marketing_lead")
            )
            .strategy(Strategy.SWARM)
            .build();

        System.out.println("--- Technical question (CEO -> Engineering -> Backend) ---");
        AgentResult result = Agentspan.run(ceo,
            "Design a REST API for a user management system with authentication "
            + "and then come up with a marketing campaign for the system");
        result.printResult();

        Agentspan.shutdown();
    }
}
