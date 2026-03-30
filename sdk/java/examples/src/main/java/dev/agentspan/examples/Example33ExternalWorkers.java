// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 33 — External Worker Tools
 *
 * <p>Demonstrates referencing Conductor workers that exist in another
 * service or language. The tool definition provides the schema and description,
 * but <em>no local worker is started</em> — Conductor dispatches the task to
 * whatever worker is polling for that task definition name.
 *
 * <p>This is useful when:
 * <ul>
 *   <li>Workers are written in Python, Go, or another language</li>
 *   <li>Workers run in a separate microservice</li>
 *   <li>You want to reuse existing Conductor task definitions</li>
 * </ul>
 *
 * <p>Mix local and external tools in the same agent. The LLM sees all tools
 * uniformly — it doesn't know which run locally vs. remotely.
 */
public class Example33ExternalWorkers {

    public static void main(String[] args) {
        // ── Local tool (runs in this JVM process) ──────────────────────────

        List<ToolDef> localTools = ToolRegistry.fromInstance(new Object() {
            @Tool(name = "format_response", description = "Format a data map into a human-readable string")
            public String formatResponse(String data) {
                return "Formatted: " + data;
            }
        });

        // ── External tool references (no func — no local worker started) ───
        // Conductor dispatches these tasks to whatever service is polling.

        ToolDef processOrder = ToolDef.builder()
            .name("process_order")
            .description("Process a customer order. Actions: refund, cancel, update.")
            .toolType("worker")  // No func → no local worker, but task def registered
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "order_id", Map.of("type", "string"),
                    "action", Map.of("type", "string")
                ),
                "required", List.of("order_id", "action")
            ))
            .build();

        ToolDef deleteAccount = ToolDef.builder()
            .name("delete_account")
            .description("Permanently delete a user account. Requires manager approval.")
            .toolType("worker")
            .approvalRequired(true)  // Human must approve before execution
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "user_id", Map.of("type", "string"),
                    "reason", Map.of("type", "string")
                ),
                "required", List.of("user_id", "reason")
            ))
            .build();

        ToolDef getCustomer = ToolDef.builder()
            .name("get_customer")
            .description("Look up customer details from the CRM system.")
            .toolType("worker")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "customer_id", Map.of("type", "string")
                ),
                "required", List.of("customer_id")
            ))
            .build();

        // ── Agent: local + external tools ─────────────────────────────────

        Agent supportAgent = Agent.builder()
            .name("support_agent_33")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a customer support agent. Use the available tools to "
                + "look up customers, process orders, and format responses. "
                + "Note: Some tools may not be available if external services are down.")
            .tools(List.of(localTools.get(0), processOrder, getCustomer))
            .build();

        System.out.println("Agent has 1 local tool + 2 external worker references.");
        System.out.println("Note: External workers (process_order, get_customer) must be running.");
        System.out.println();

        AgentResult result = Agentspan.run(supportAgent,
            "Format a summary: Customer C-1234 needs their order ORD-5678 processed for cancellation.");
        result.printResult();

        Agentspan.shutdown();
    }
}
