// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.frameworks.LangChainBridge;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.GuardrailDef;
import ai.agentspan.model.GuardrailResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.regex.Pattern;

/**
 * Example LangChain 26 — Agentspan guardrails on a native LangChain4j agent.
 *
 * <p>LangChain4j has no built-in guardrail abstraction. Agentspan provides a
 * server-compiled guardrail mechanism that runs as a Conductor task inside the
 * agent's loop. This example attaches a PII-redaction guardrail to a pure
 * LangChain4j agent built from a native {@code ChatModel}.
 *
 * <p>Pattern (same as
 * {@code adk.Example38AgentspanGuardrails}):
 * <ol>
 *   <li>Build native LangChain4j {@code ChatModel}.</li>
 *   <li>Hand it to {@link LangChainBridge#agentBuilder} (the builder variant
 *       lets you decorate before building).</li>
 *   <li>Attach a {@link GuardrailDef} with {@link OnFail#FIX} so the
 *       guardrail rewrites the output in place.</li>
 *   <li>{@link Agentspan#run}.</li>
 * </ol>
 */
public class Example26AgentspanGuardrails {

    private static final Pattern EMAIL = Pattern.compile(
            "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b");
    private static final Pattern PHONE = Pattern.compile(
            "\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b");

    private static GuardrailResult redactPii(String content) {
        String redacted = content;
        redacted = EMAIL.matcher(redacted).replaceAll("[EMAIL REDACTED]");
        redacted = PHONE.matcher(redacted).replaceAll("[PHONE REDACTED]");
        if (redacted.equals(content)) {
            return GuardrailResult.pass();
        }
        return GuardrailResult.fix(redacted);
    }

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
                .apiKey("agentspan-server-handles-credentials")
                .modelName("gpt-4o-mini")
                .build();

        GuardrailDef piiRedaction = GuardrailDef.builder()
                .name("pii_redaction")
                .position(Position.OUTPUT)
                .onFail(OnFail.FIX)
                .maxRetries(1)
                .func(Example26AgentspanGuardrails::redactPii)
                .build();

        Agent guarded = LangChainBridge.agentBuilder(
                "contact_directory_lc",
                model,
                "You are the support directory assistant. The user will supply contact "
                + "details and ask you to confirm them. Always echo the details back "
                + "verbatim — another safety layer scrubs anything sensitive.")
                .guardrails(piiRedaction)
                .build();

        AgentResult result = Agentspan.run(guarded,
                "Please confirm: alice@example.com and 555-867-5309. "
                + "Echo them back so I can double-check the spelling.");
        result.printResult();

        Agentspan.shutdown();
    }
}
