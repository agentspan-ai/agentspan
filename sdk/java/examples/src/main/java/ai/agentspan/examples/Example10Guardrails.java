// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.GuardrailDef;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.OnFail;
import ai.agentspan.enums.Position;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.GuardrailResult;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Example 10 — Guardrails
 *
 * <p>Demonstrates an output guardrail that catches PII leaking from tool results.
 * If the agent includes raw credit card numbers in its response, the guardrail
 * fails with on_fail=RETRY so the agent retries with feedback to redact PII.
 */
public class Example10Guardrails {

    static class CustomerTools {
        @Tool(name = "get_order_status", description = "Look up the current status of an order")
        public Map<String, Object> getOrderStatus(String orderId) {
            return Map.of(
                "order_id", orderId,
                "status", "shipped",
                "tracking", "1Z999AA10123456784",
                "estimated_delivery", "2026-02-22"
            );
        }

        @Tool(name = "get_customer_info", description = "Retrieve customer details including payment info on file")
        public Map<String, Object> getCustomerInfo(String customerId) {
            return Map.of(
                "customer_id", customerId,
                "name", "Alice Johnson",
                "email", "alice@example.com",
                "card_on_file", "4532-0150-1234-5678",
                "membership", "gold"
            );
        }
    }

    static class PiiGuardrails {
        private static final Pattern CC_PATTERN =
            Pattern.compile("\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b");
        private static final Pattern SSN_PATTERN =
            Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b");

        @GuardrailDef(
            name = "no_pii",
            position = Position.OUTPUT,
            onFail = OnFail.RETRY
        )
        public GuardrailResult noPii(String content) {
            if (CC_PATTERN.matcher(content).find() || SSN_PATTERN.matcher(content).find()) {
                return GuardrailResult.fail(
                    "Your response contains PII (credit card or SSN). "
                    + "Redact all card numbers and SSNs before responding.");
            }
            return GuardrailResult.pass();
        }
    }

    public static void main(String[] args) {
        List<ai.agentspan.model.ToolDef> tools = ToolRegistry.fromInstance(new CustomerTools());
        List<ai.agentspan.model.GuardrailDef> guardrails =
            ToolRegistry.guardrailsFromInstance(new PiiGuardrails());

        Agent agent = Agent.builder()
            .name("support_agent")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a customer support assistant. Use the available tools to "
                + "answer questions about orders and customers. Always include all "
                + "details from the tool results in your response.")
            .tools(tools)
            .guardrails(guardrails)
            .build();

        AgentResult result = Agentspan.run(agent,
            "I need a full summary: What's the status of order ORD-42, "
            + "and what's the profile for customer CUST-7?");
        result.printResult();

        if (result.isSuccess() && result.getOutput(String.class) != null
                && result.getOutput(String.class).contains("4532-0150-1234-5678")) {
            System.out.println("[WARN] PII leaked through the guardrail!");
        } else {
            System.out.println("[OK] PII was redacted from the final output.");
        }

        Agentspan.shutdown();
    }
}
