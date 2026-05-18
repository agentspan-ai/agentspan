// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.GuardrailDef;

import java.util.List;
import java.util.Map;

/**
 * Example 22 — LLM Guardrails (AI-powered content safety evaluation)
 *
 * <p>Demonstrates {@code guardrailType="llm"} which uses a separate LLM to
 * evaluate whether agent output meets a policy. The guardrail LLM receives
 * the policy + content and judges pass/fail.
 *
 * <p>The agent is compiled with a DoWhile loop that retries the LLM call
 * when the guardrail fails — same durable retry behavior as other guardrails.
 */
public class Example22LlmGuardrails {

    public static void main(String[] args) {
        // ── LLM-based tone guardrail ───────────────────────────────────────
        // Ensures customer communications are professional and positive.

        GuardrailDef toneGuard = GuardrailDef.builder()
            .name("tone_check")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(3)
            .guardrailType("llm")
            .config(Map.of(
                "model", Settings.LLM_MODEL,
                "policy",
                    "Reject any content that:\n"
                    + "1. Uses rude, dismissive, or condescending language\n"
                    + "2. Contains profanity or offensive terms\n"
                    + "3. Makes absolute guarantees about product performance\n"
                    + "4. Reveals confidential pricing or internal business information\n"
                    + "\n"
                    + "Approve content that is professional, helpful, and courteous.",
                "maxTokens", 10000
            ))
            .build();

        // ── Agent with LLM guardrail ───────────────────────────────────────

        Agent agent = Agent.builder()
            .name("customer_comm_agent")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a professional customer communications writer. "
                + "Write helpful, polite, and solution-focused responses. "
                + "Always maintain a positive and respectful tone.")
            .guardrails(List.of(toneGuard))
            .build();

        AgentResult result = Agentspan.run(agent,
            "A customer is frustrated that their order arrived late. Write a response.");
        result.printResult();

        Agentspan.shutdown();
    }
}
