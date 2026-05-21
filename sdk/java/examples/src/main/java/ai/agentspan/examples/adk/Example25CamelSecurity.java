// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.internal.JsonMapper;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

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

    @Schema(description = "Fetch user data from the database.")
    public static Map<String, Object> fetchUserData(
            @Schema(name = "user_id", description = "User ID") String userId) {
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

    @Schema(description = "Redact sensitive fields from data before responding to users.")
    public static Map<String, Object> redactSensitiveFields(
            @Schema(name = "data", description = "JSON-encoded data to redact") String data) {
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

    public static void main(String[] args) {
        LlmAgent collector = LlmAgent.builder()
            .name("data_collector")
            .description("Fetches raw user data and forwards it to the security validator.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a data collection pipeline. When asked about a user,
                call fetch_user_data with their ID. Pass the raw data along
                to the next pipeline for security review.
                """)
            .tools(FunctionTool.create(Example25CamelSecurity.class, "fetchUserData"))
            .build();

        LlmAgent validator = LlmAgent.builder()
            .name("security_validator")
            .description("Redacts sensitive fields (SSN, balances, emails) from collected data.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a security validator. Review data for sensitive information
                (SSN, account balances, email addresses). Use the redact_sensitive_fields
                tool to redact any sensitive data before passing it along.
                Only pass redacted data to the next pipeline.
                """)
            .tools(FunctionTool.create(Example25CamelSecurity.class, "redactSensitiveFields"))
            .build();

        LlmAgent responder = LlmAgent.builder()
            .name("responder")
            .description("Answers the user using only the validated, redacted data.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a customer service pipeline. Use the validated, redacted data
                to answer the user's question. NEVER reveal redacted information.
                If data shows ***REDACTED***, explain that the information is
                restricted for security reasons.
                """)
            .build();

        LlmAgent pipeline = LlmAgent.builder()
            .name("secure_data_pipeline")
            .description("CaMeL-style sequential pipeline: collect → redact → respond.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate a secure data pipeline. Run sub-agents sequentially:
                1) data_collector fetches raw user data, 2) security_validator redacts
                sensitive fields, 3) responder formats the final answer using only
                the redacted data.
                """)
            .subAgents(collector, validator, responder)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Tell me everything about user U001 including their financial details.");
        result.printResult();

        Agentspan.shutdown();
    }
}
