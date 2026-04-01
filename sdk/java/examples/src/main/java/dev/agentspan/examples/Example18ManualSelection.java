// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentHandle;
import dev.agentspan.model.AgentResult;

import java.util.List;
import java.util.Map;

/**
 * Example 18 — Manual Agent Selection (programmatic simulation)
 *
 * <p>Demonstrates {@code Strategy.MANUAL} where an operator decides which
 * sub-agent responds on each turn. The workflow pauses at a HumanTask after
 * each turn, waiting for a {@code {"selected": "<agent_name>"}} response.
 *
 * <p>In this example the selections are driven programmatically to make the
 * example fully runnable end-to-end. In a real application a UI would present
 * the agent choices and a human would make the selection.
 *
 * <pre>
 * editorial_team (MANUAL, 3 turns)
 *   turn 1 → writer       (auto-selected)
 *   turn 2 → fact_checker (auto-selected)
 *   turn 3 → editor       (auto-selected)
 * </pre>
 */
public class Example18ManualSelection {

    public static void main(String[] args) {
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

        Agent editorialTeam = Agent.builder()
            .name("editorial_team")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You coordinate an editorial team. A human operator selects "
                + "which team member responds on each turn.")
            .agents(writer, editor, factChecker)
            .strategy(Strategy.MANUAL)
            .maxTurns(3)
            .build();

        String prompt =
            "Draft a short paragraph about the discovery of penicillin, "
            + "then have it reviewed for accuracy and style.";

        AgentHandle handle = Agentspan.start(editorialTeam, prompt);
        System.out.println("Workflow ID: " + handle.getWorkflowId());

        // Drive the 3 manual turns. Each turn the MANUAL strategy creates a
        // HumanTask and sets isWaiting=true. We poll for that state, then send
        // the selection. After the last turn the workflow completes.
        List<String> selections = List.of("writer", "fact_checker", "editor");

        for (int i = 0; i < selections.size(); i++) {
            String agentName = selections.get(i);

            boolean waiting = handle.waitUntilWaiting(120_000);
            if (!waiting) {
                System.out.println("Turn " + (i + 1) + ": workflow completed before selection");
                break;
            }
            handle.respond(Map.of("selected", agentName));
            System.out.println("Turn " + (i + 1) + ": selected '" + agentName + "'");
        }

        // Wait for final completion
        AgentResult result = handle.waitForResult();
        result.printResult();

        Agentspan.shutdown();
    }
}
