// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.examples.Settings;
import ai.agentspan.frameworks.AdkBridge;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.GuardrailDef;
import ai.agentspan.model.GuardrailResult;

import com.google.adk.agents.LlmAgent;

import java.util.regex.Pattern;

/**
 * Example Adk 38 — Agentspan guardrails on a native ADK agent
 *
 * <p>ADK itself doesn't ship a guardrail abstraction — its safety story is
 * {@code beforeModelCallback} returning a short-circuit response, which the
 * server doesn't yet compile into hook tasks (see Example23). Agentspan
 * provides a separate, server-compiled guardrail mechanism that runs as a
 * Conductor task inside the agent's loop. This example shows how to attach
 * Agentspan guardrails to a pure ADK agent without giving up the drop-in
 * pattern.
 *
 * <p>Pattern:
 * <ol>
 *   <li>Build the native ADK {@link LlmAgent} exactly as you would for ADK.</li>
 *   <li>Hand it to {@link AdkBridge#agentBuilder} (NOT {@code toAgentspan} —
 *       the builder variant lets you decorate before building).</li>
 *   <li>Attach a {@link GuardrailDef} with a validation function that
 *       returns {@link GuardrailResult#pass()}, {@link GuardrailResult#fail
 *       fail(message)}, or {@link GuardrailResult#fix fix(rewrittenOutput)}.</li>
 *   <li>{@link Agentspan#run} executes the agent with the guardrail running
 *       server-side after each LLM turn; failures retry (up to
 *       {@code maxRetries}) or fix-substitute depending on {@link OnFail}.</li>
 * </ol>
 *
 * <p>This guardrail redacts PII (email, phone, SSN, credit card) from the
 * model's response using {@code OnFail.FIX} so the LLM doesn't have to
 * regenerate — the guardrail rewrites the output in place.
 */
public class Example38AgentspanGuardrails {

    private static final Pattern EMAIL = Pattern.compile(
            "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b");
    private static final Pattern PHONE = Pattern.compile(
            "\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b");
    private static final Pattern SSN = Pattern.compile(
            "\\b\\d{3}-\\d{2}-\\d{4}\\b");
    private static final Pattern CREDIT_CARD = Pattern.compile(
            "\\b\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}\\b");

    /** Returns a redacted copy of the response, or {@link GuardrailResult#pass()} if clean. */
    private static GuardrailResult redactPii(String content) {
        String redacted = content;
        redacted = EMAIL.matcher(redacted).replaceAll("[EMAIL REDACTED]");
        redacted = PHONE.matcher(redacted).replaceAll("[PHONE REDACTED]");
        redacted = SSN.matcher(redacted).replaceAll("[SSN REDACTED]");
        redacted = CREDIT_CARD.matcher(redacted).replaceAll("[CARD REDACTED]");
        if (redacted.equals(content)) {
            return GuardrailResult.pass();
        }
        // Server-side guardrail compiler honours OnFail.FIX by substituting
        // `fixed_output` for the LLM's response — the run completes after this
        // single rewrite rather than re-asking the LLM.
        return GuardrailResult.fix(redacted);
    }

    public static void main(String[] args) {
        LlmAgent helper = LlmAgent.builder()
                .name("contact_directory")
                .description("Confirms contact details the user has just supplied.")
                .model(Settings.LLM_MODEL)
                .instruction("""
                        You are the support directory assistant. The user will supply
                        contact details and ask you to confirm or summarize them. Always
                        echo the details back verbatim in a friendly summary sentence —
                        another safety layer is responsible for redacting anything
                        sensitive before the user sees your reply.
                        """)
                .build();

        GuardrailDef piiRedaction = GuardrailDef.builder()
                .name("pii_redaction")
                .position(Position.OUTPUT)
                .onFail(OnFail.FIX)
                .maxRetries(1)
                .func(Example38AgentspanGuardrails::redactPii)
                .build();

        // Drop in the native ADK agent, then bolt Agentspan's server-side
        // guardrail onto the bridged builder before .build().
        Agent guarded = AdkBridge.agentBuilder(helper)
                .guardrails(piiRedaction)
                .build();

        AgentResult result = Agentspan.run(guarded,
                "Please confirm the contact details I just sent: alice@example.com "
                + "and phone 555-867-5309. Echo them back in your reply so I can "
                + "double-check the spelling.");
        result.printResult();

        Agentspan.shutdown();
    }
}
