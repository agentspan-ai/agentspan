// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.ScatterGather;
import dev.agentspan.model.AgentResult;

/**
 * Example 58 — Scatter-Gather Pattern
 *
 * <p>Demonstrates a coordinator that fans out a research task to a worker agent
 * running in parallel for each country, then synthesizes the results.
 *
 * <pre>
 * coordinator (ScatterGather)
 *   └── country_researcher × N (parallel)
 * </pre>
 */
public class Example58ScatterGather {

    public static void main(String[] args) {
        // ── Worker: analyses a single country's tech ecosystem ───────────────

        Agent countryResearcher = Agent.builder()
            .name("country_researcher_58")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a technology market analyst. When given a country name, write a " +
                "concise 100-word report covering: top tech companies, main tech sectors, " +
                "notable recent innovations, and a one-sentence investment outlook.")
            .build();

        // ── Coordinator: scatters to worker, gathers results ─────────────────

        Agent coordinator = ScatterGather.create(
            "tech_coordinator_58",
            countryResearcher,
            Settings.LLM_MODEL,
            "After gathering all country reports, produce a 5-bullet executive summary " +
            "highlighting the top global tech trends across all countries.",
            300);

        System.out.println("=== Scatter-Gather: Tech Ecosystem Analysis ===");
        AgentResult result = Agentspan.run(coordinator,
            "Analyse the technology ecosystems of the following 8 countries in parallel: " +
            "USA, China, India, Germany, Israel, South Korea, Canada, Brazil. " +
            "Call country_researcher_58 ONCE PER COUNTRY simultaneously, then summarize.");
        result.printResult();

        Agentspan.shutdown();
    }
}
