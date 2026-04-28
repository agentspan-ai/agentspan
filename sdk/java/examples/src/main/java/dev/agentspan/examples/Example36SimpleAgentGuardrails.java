// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;

import java.util.List;
import java.util.Map;

/**
 * Example 36 — Simple Agent Guardrails (output validation without tools)
 *
 * <p>Demonstrates guardrails on a simple agent (no tools, no sub-agents).
 * Uses two guardrail types:
 * <ul>
 *   <li>Regex guardrail (server-side) — blocks bullet-point lists</li>
 *   <li>Custom guardrail function — enforces minimum word count</li>
 * </ul>
 *
 * <p>The agent retries automatically when a guardrail fails (DoWhile loop
 * compiled server-side).
 */
public class Example36SimpleAgentGuardrails {

    public static void main(String[] args) {
        // ── Regex guardrail: block bullet-point lists (server-side InlineTask) ─

        GuardrailDef noBulletLists = GuardrailDef.builder()
            .name("no_lists")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(3)
            .guardrailType("regex")
            .config(Map.of(
                "patterns", List.of("^\\s*[-*]\\s", "^\\s*\\d+\\.\\s"),
                "mode", "block",
                "message",
                    "Do not use bullet points or numbered lists. "
                    + "Write in flowing prose paragraphs instead."
            ))
            .build();

        // ── Custom guardrail: enforce minimum length (client-side worker) ──

        GuardrailDef minLength = GuardrailDef.builder()
            .name("min_length")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(3)
            .func(content -> {
                int wordCount = content.split("\\s+").length;
                if (wordCount < 50) {
                    return GuardrailResult.fail(
                        String.format(
                            "Response is too short (%d words). "
                            + "Please provide a more detailed answer with at least 50 words.",
                            wordCount
                        )
                    );
                }
                return GuardrailResult.pass();
            })
            .build();

        // ── Agent (no tools) ───────────────────────────────────────────────

        Agent agent = Agent.builder()
            .name("essay_writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a concise essay writer. Answer the user's question in "
                + "well-structured prose paragraphs. Do NOT use bullet points or "
                + "numbered lists.")
            .guardrails(List.of(noBulletLists, minLength))
            .build();

        AgentResult result = Agentspan.run(agent, "Explain why the sky is blue.");
        result.printResult();

        Agentspan.shutdown();
    }
}
