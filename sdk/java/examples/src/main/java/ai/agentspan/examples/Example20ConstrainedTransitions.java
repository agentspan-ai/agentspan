// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;

import java.util.List;
import java.util.Map;

/**
 * Example 20 — Constrained Speaker Transitions (code review workflow)
 *
 * <p>Demonstrates {@code allowedTransitions} which restricts which agent can
 * speak after which in a ROUND_ROBIN discussion. Useful for enforcing
 * conversational protocols.
 *
 * <p>Code review protocol:
 * <ul>
 *   <li>developer → reviewer (code must be reviewed)</li>
 *   <li>reviewer → developer OR approver (send back or escalate)</li>
 *   <li>approver → developer (request revisions)</li>
 * </ul>
 */
public class Example20ConstrainedTransitions {

    public static void main(String[] args) {
        Agent developer = Agent.builder()
            .name("developer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a software developer. Write or revise code based on feedback. "
                + "Keep responses focused on code changes.")
            .build();

        Agent reviewer = Agent.builder()
            .name("reviewer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a code reviewer. Review the developer's code for bugs, style, "
                + "and best practices. Provide specific, actionable feedback.")
            .build();

        Agent approver = Agent.builder()
            .name("approver")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are the tech lead. Review the code and feedback. Either approve "
                + "the code or request revisions with specific guidance.")
            .build();

        // Constrained transitions enforce the review protocol
        Agent codeReview = Agent.builder()
            .name("code_review")
            .model(Settings.LLM_MODEL)
            .agents(developer, reviewer, approver)
            .strategy(Strategy.ROUND_ROBIN)
            .maxTurns(6)
            .allowedTransitions(Map.of(
                "developer", List.of("reviewer"),
                "reviewer", List.of("developer", "approver"),
                "approver", List.of("developer")
            ))
            .build();

        AgentResult result = Agentspan.run(codeReview,
            "Write a Python function to validate email addresses using regex.");
        result.printResult();

        Agentspan.shutdown();
    }
}
