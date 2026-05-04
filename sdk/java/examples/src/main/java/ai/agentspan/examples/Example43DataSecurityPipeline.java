// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 43 — Data Security Pipeline (controlled data flow with redaction)
 *
 * <p>Demonstrates a sequential pipeline with data flow control where
 * sensitive information is collected, redacted, and then presented safely:
 *
 * <pre>
 * data_collector → security_validator → responder
 * </pre>
 *
 * <ul>
 *   <li>collector: Fetches raw user data (includes PII)</li>
 *   <li>validator: Redacts sensitive fields (SSN, balance, email)</li>
 *   <li>responder: Presents the safe, redacted data to the user</li>
 * </ul>
 *
 * This pattern enforces a security boundary — PII never reaches the final output.
 */
public class Example43DataSecurityPipeline {

    static class CollectorTools {
        @Tool(name = "fetch_user_data", description = "Fetch user data from the database")
        public Map<String, Object> fetchUserData(String userId) {
            Map<String, Map<String, Object>> users = Map.of(
                "U001", Map.of(
                    "name", "Alice Johnson",
                    "email", "alice@example.com",
                    "role", "admin",
                    "ssn_last4", "1234",
                    "account_balance", 15000.00
                ),
                "U002", Map.of(
                    "name", "Bob Smith",
                    "email", "bob@example.com",
                    "role", "user",
                    "ssn_last4", "5678",
                    "account_balance", 3200.00
                )
            );
            return users.getOrDefault(userId, Map.of("error", "User " + userId + " not found"));
        }
    }

    static class ValidatorTools {
        private static final java.util.Set<String> SENSITIVE_KEYS =
            java.util.Set.of("ssn_last4", "account_balance", "email");

        @Tool(name = "redact_sensitive_fields", description = "Redact sensitive fields from data before responding to users")
        public Map<String, Object> redactSensitiveFields(String data) {
            // Parse simple key=value from stringified map representation
            Map<String, Object> redacted = new java.util.LinkedHashMap<>();
            // Try to parse as JSON-like string using simple heuristics
            String[] pairs = data.replaceAll("[{}]", "").split(",");
            for (String pair : pairs) {
                String[] kv = pair.split("=", 2);
                if (kv.length == 2) {
                    String key = kv[0].trim().replaceAll("[\"'\\s]", "");
                    String value = kv[1].trim().replaceAll("[\"'\\s]", "");
                    redacted.put(key, SENSITIVE_KEYS.contains(key) ? "***REDACTED***" : value);
                }
            }
            return Map.of("redacted_data", redacted.isEmpty()
                ? Map.of("note", "Data processed — sensitive fields redacted") : redacted);
        }
    }

    public static void main(String[] args) {
        List<ToolDef> collectorTools = ToolRegistry.fromInstance(new CollectorTools());
        List<ToolDef> validatorTools = ToolRegistry.fromInstance(new ValidatorTools());

        // Data collector fetches raw user data
        Agent collector = Agent.builder()
            .name("data_collector")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a data collection agent. When asked about a user, "
                + "call fetch_user_data with their ID. Pass the raw data along "
                + "to the next agent for security review.")
            .tools(collectorTools)
            .build();

        // Validator enforces data security policy
        Agent validator = Agent.builder()
            .name("security_validator")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a security validator. Review data for sensitive information "
                + "(SSN, account balances, email addresses). Use redact_sensitive_fields "
                + "to redact any sensitive data before passing it along. "
                + "Only pass redacted data to the next agent.")
            .tools(validatorTools)
            .build();

        // Responder formats the final answer
        Agent responder = Agent.builder()
            .name("responder")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a customer service agent. Use the validated, redacted data "
                + "to answer the user's question. NEVER reveal redacted information. "
                + "If data shows ***REDACTED***, explain that information is "
                + "restricted for security reasons.")
            .build();

        // Sequential pipeline: collect → validate → respond
        Agent pipeline = Agent.builder()
            .name("data_security_pipeline")
            .model(Settings.LLM_MODEL)
            .agents(collector, validator, responder)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Tell me everything about user U001 including their financial details.");
        result.printResult();

        Agentspan.shutdown();
    }
}
