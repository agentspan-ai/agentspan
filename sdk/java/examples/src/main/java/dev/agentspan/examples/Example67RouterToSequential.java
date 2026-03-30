// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 67 — Router to Sequential (route to a pipeline sub-agent)
 *
 * <p>Demonstrates a router that selects between a single agent (for quick
 * answers) and a sequential pipeline (for research tasks requiring
 * multiple stages).
 *
 * <pre>
 * team_67 (ROUTER, router=selector_67)
 * ├── quick_answer_67           (single agent)
 * └── research_pipeline_67      (SEQUENTIAL)
 *     ├── researcher_67
 *     └── writer_67
 * </pre>
 *
 * The router agent decides which path to take based on the request.
 */
public class Example67RouterToSequential {

    public static void main(String[] args) {
        // ── Quick answer (single agent) ────────────────────────────────────

        Agent quickAnswer = Agent.builder()
            .name("quick_answer_67")
            .model(Settings.LLM_MODEL)
            .instructions("You give quick, 1-2 sentence answers to simple questions.")
            .build();

        // ── Research pipeline (sequential) ────────────────────────────────

        Agent researchPipeline = Agent.builder()
            .name("research_pipeline_67")
            .model(Settings.LLM_MODEL)
            .instructions("Run the researcher first, then pass findings to the writer.")
            .agents(
                Agent.builder()
                    .name("researcher_67")
                    .model(Settings.LLM_MODEL)
                    .instructions(
                        "You are a researcher. Research the topic and provide "
                        + "3-5 key facts with supporting details.")
                    .build(),
                Agent.builder()
                    .name("writer_67")
                    .model(Settings.LLM_MODEL)
                    .instructions(
                        "You are a writer. Take the research findings and write a clear, "
                        + "engaging summary. Use headers and bullet points.")
                    .build()
            )
            .strategy(Strategy.SEQUENTIAL)
            .build();

        // ── Router agent (selector) ────────────────────────────────────────

        Agent selector = Agent.builder()
            .name("selector_67")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a request classifier. Select the right team member:\n"
                + "- quick_answer_67: for simple factual questions with short answers\n"
                + "- research_pipeline_67: for research tasks requiring analysis and writing")
            .build();

        // ── Team with router ───────────────────────────────────────────────

        Agent team = Agent.builder()
            .name("team_67")
            .model(Settings.LLM_MODEL)
            .instructions("Route requests to the appropriate sub-agent or pipeline.")
            .agents(quickAnswer, researchPipeline)
            .strategy(Strategy.ROUTER)
            .router(selector)
            .build();

        System.out.println("=== Scenario 1: Research task (router → sequential pipeline) ===");
        AgentResult r1 = Agentspan.run(team,
            "Research the current state of quantum computing and write a summary.");
        r1.printResult();

        System.out.println("\n=== Scenario 2: Quick question (router → single agent) ===");
        AgentResult r2 = Agentspan.run(team,
            "What is the capital of France?");
        r2.printResult();

        Agentspan.shutdown();
    }
}
