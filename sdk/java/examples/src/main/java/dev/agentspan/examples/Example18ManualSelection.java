// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentHandle;

/**
 * Example 18 — Manual Agent Selection (human-in-the-loop orchestration)
 *
 * <p>Demonstrates {@code Strategy.MANUAL} where a human operator decides
 * which sub-agent responds on each turn. Instead of the LLM or a fixed
 * rotation choosing the next speaker, the workflow pauses and waits for
 * an explicit selection before proceeding.
 *
 * <p>This is useful for editorial review, compliance workflows, or any
 * scenario where a human must stay in control of the conversational flow.
 *
 * <p>Flow:
 * <ol>
 *   <li>The {@code editorial_team} agent starts with {@code Strategy.MANUAL}</li>
 *   <li>After each turn the workflow pauses for operator input</li>
 *   <li>The operator selects the next agent via the Conductor UI or
 *       {@code handle.respond({"selected": "writer"})} calls</li>
 *   <li>The chosen sub-agent produces its response and the cycle repeats
 *       up to {@code maxTurns}</li>
 * </ol>
 *
 * <p>This example starts the workflow and prints the workflow ID. Actual
 * agent-selection interactions must be performed externally (Conductor UI
 * or programmatic {@code handle.respond()} calls).
 */
public class Example18ManualSelection {

    public static void main(String[] args) {
        // ── Sub-agents ───────────────────────────────────────────────────

        Agent writer = Agent.builder()
            .name("writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a creative writer. Draft compelling, vivid prose. "
                + "Prioritise narrative flow and reader engagement.")
            .build();

        Agent editor = Agent.builder()
            .name("editor")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a strict editor. Review the content for grammar, "
                + "clarity, and structure. Be direct and precise.")
            .build();

        Agent factChecker = Agent.builder()
            .name("fact_checker")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a meticulous fact-checker. Verify the accuracy of "
                + "claims in the content and flag anything unsubstantiated.")
            .build();

        // ── Editorial team with MANUAL strategy ─────────────────────────
        // Each turn the workflow pauses and waits for the operator to choose
        // which agent responds next.

        Agent editorialTeam = Agent.builder()
            .name("editorial_team")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You coordinate an editorial team. A human operator will select "
                + "which team member responds on each turn.")
            .agents(writer, editor, factChecker)
            .strategy(Strategy.MANUAL)
            .maxTurns(3)
            .build();

        // ── Start the workflow (fire-and-forget) ─────────────────────────
        // Agentspan.start() submits the workflow and returns immediately.
        // The workflow pauses at each turn, waiting for the operator to pick
        // the next agent.

        String prompt =
            "Draft a short paragraph about the discovery of penicillin, "
            + "then have it reviewed for accuracy and style.";

        AgentHandle handle = Agentspan.start(editorialTeam, prompt);

        System.out.println("Editorial team workflow started.");
        System.out.println("Workflow ID: " + handle.getWorkflowId());
        System.out.println();

        // ── Interaction instructions ─────────────────────────────────────
        // This example requires manual interaction. To drive the workflow
        // programmatically you would call handle.respond() with the selected
        // agent name, for example:
        //
        //   handle.respond("{\"selected\": \"writer\"}");
        //   handle.respond("{\"selected\": \"fact_checker\"}");
        //   handle.respond("{\"selected\": \"editor\"}");
        //
        // Or monitor and interact through the Conductor UI.

        System.out.println(
            "This example requires manual interaction. "
            + "Monitor at the Conductor UI or use "
            + "handle.respond({\"selected\": \"writer\"}) to pick agents.");

        Agentspan.shutdown();
    }
}
