// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.internal.JsonMapper;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Example Adk 25 — CaMeL Security
 *
 * <p>Java port of <code>sdk/python/examples/adk/25_camel_security.py</code>.
 *
 * <p>Demonstrates: a CaMeL-inspired sequential pipeline
 * (collector → validator → responder) enforcing controlled data flow and
 * redacting sensitive fields before responding to users.
 */
public class Example25CamelSecurity {

    static class CollectorTools {

        @Tool(name = "fetch_user_data", value = "Fetch user data from the database.")
        public Map<String, Object> fetchUserData(@P("user_id") String userId) {
            Map<String, Map<String, Object>> users = new LinkedHashMap<>();
            users.put("U001", Map.of(
                "name", "Alice Johnson",
                "email", "alice@example.com",
                "role", "admin",
                "ssn_last4", "1234",
                "account_balance", 15000.00
            ));
            users.put("U002", Map.of(
                "name", "Bob Smith",
                "email", "bob@example.com",
                "role", "user",
                "ssn_last4", "5678",
                "account_balance", 3200.00
            ));
            return users.getOrDefault(userId, Map.of("error", "User " + userId + " not found"));
        }
    }

    static class ValidatorTools {

        @Tool(name = "redact_sensitive_fields", value = "Redact sensitive fields from data before responding to users.")
        public Map<String, Object> redactSensitiveFields(@P("data") String data) {
            Map<?, ?> parsed;
            try {
                parsed = JsonMapper.get().readValue(data, Map.class);
            } catch (Exception e) {
                return Map.of("error", "Could not parse data for redaction");
            }
            Set<String> sensitiveKeys = Set.of("ssn_last4", "account_balance", "email");
            Map<String, Object> redacted = new LinkedHashMap<>();
            for (Map.Entry<?, ?> e : parsed.entrySet()) {
                String k = String.valueOf(e.getKey());
                if (sensitiveKeys.contains(k)) {
                    redacted.put(k, "***REDACTED***");
                } else {
                    redacted.put(k, e.getValue());
                }
            }
            return Map.of("redacted_data", redacted);
        }
    }

    public static void main(String[] args) {
        Agent collector = GoogleADKAgent.builder()
            .name("data_collector")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a data collection agent. When asked about a user, "
                + "call fetch_user_data with their ID. Pass the raw data along "
                + "to the next agent for security review.")
            .tools(new CollectorTools())
            .build();

        Agent validator = GoogleADKAgent.builder()
            .name("security_validator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a security validator. Review data for sensitive information "
                + "(SSN, account balances, email addresses). Use the redact_sensitive_fields "
                + "tool to redact any sensitive data before passing it along. "
                + "Only pass redacted data to the next agent.")
            .tools(new ValidatorTools())
            .build();

        Agent responder = GoogleADKAgent.builder()
            .name("responder")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a customer service agent. Use the validated, redacted data "
                + "to answer the user's question. NEVER reveal redacted information. "
                + "If data shows ***REDACTED***, explain that the information is "
                + "restricted for security reasons.")
            .build();

        Agent pipeline = GoogleADKAgent.builder()
            .name("secure_data_pipeline")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate a secure data pipeline. Run sub-agents sequentially: "
                + "1) data_collector fetches raw user data, 2) security_validator redacts "
                + "sensitive fields, 3) responder formats the final answer using only "
                + "the redacted data.")
            .subAgents(collector, validator, responder)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Tell me everything about user U001 including their financial details.");
        result.printResult();

        Agentspan.shutdown();
    }
}
