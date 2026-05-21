// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 16 — Customer Service
 *
 * <p>Java port of <code>sdk/python/examples/adk/16_customer_service.py</code>.
 *
 * <p>Demonstrates: a single agent with multiple domain-specific tools that
 * handles customer inquiries end-to-end (account, billing, ticket, plan).
 */
public class Example16CustomerService {

    @Schema(description = "Retrieve account details for a customer.")
    public static Map<String, Object> getAccountDetails(
            @Schema(name = "account_id", description = "Account ID") String accountId) {
        Map<String, Map<String, Object>> accounts = new LinkedHashMap<>();
        accounts.put("ACC-001", Map.of(
            "name", "Alice Johnson",
            "email", "alice@example.com",
            "plan", "Premium",
            "balance", 142.50,
            "status", "active"));
        accounts.put("ACC-002", Map.of(
            "name", "Bob Martinez",
            "email", "bob@example.com",
            "plan", "Basic",
            "balance", 0.00,
            "status", "active"));
        return accounts.getOrDefault(accountId.toUpperCase(),
            Map.of("error", "Account " + accountId + " not found"));
    }

    @Schema(description = "Get billing history for an account.")
    public static Map<String, Object> getBillingHistory(
            @Schema(name = "account_id", description = "Account ID") String accountId,
            @Schema(name = "num_months", description = "Number of months of history") int numMonths) {
        Map<String, List<Map<String, Object>>> history = new LinkedHashMap<>();
        history.put("ACC-001", List.of(
            Map.of("month", "March 2025", "amount", 49.99, "status", "paid"),
            Map.of("month", "February 2025", "amount", 49.99, "status", "paid"),
            Map.of("month", "January 2025", "amount", 42.50, "status", "paid")
        ));
        List<Map<String, Object>> records = history.getOrDefault(accountId.toUpperCase(), new ArrayList<>());
        int n = numMonths <= 0 ? 3 : numMonths;
        return Map.of("account_id", accountId,
            "billing_history", records.subList(0, Math.min(n, records.size())));
    }

    @Schema(description = "Submit a support ticket for a customer issue.")
    public static Map<String, Object> submitSupportTicket(
            @Schema(name = "account_id", description = "Account ID") String accountId,
            @Schema(name = "category", description = "Ticket category") String category,
            @Schema(name = "description", description = "Issue description") String description) {
        List<String> validCategories = List.of("billing", "technical", "account", "general");
        if (!validCategories.contains(category.toLowerCase())) {
            return Map.of("error", "Invalid category. Must be one of: " + validCategories);
        }
        return Map.of(
            "ticket_id", "TKT-2025-0042",
            "account_id", accountId,
            "category", category,
            "status", "open",
            "message", "Ticket created for " + category + " issue"
        );
    }

    @Schema(description = "Update the subscription plan for an account.")
    public static Map<String, Object> updateAccountPlan(
            @Schema(name = "account_id", description = "Account ID") String accountId,
            @Schema(name = "new_plan", description = "Target plan name") String newPlan) {
        Map<String, Double> plans = new LinkedHashMap<>();
        plans.put("basic", 19.99);
        plans.put("premium", 49.99);
        plans.put("enterprise", 99.99);
        Double price = plans.get(newPlan.toLowerCase());
        if (price == null) {
            return Map.of("error", "Invalid plan. Available: " + plans.keySet());
        }
        return Map.of(
            "status", "success",
            "account_id", accountId,
            "new_plan", newPlan,
            "new_price", "$" + price + "/month",
            "effective_date", "Next billing cycle"
        );
    }

    public static void main(String[] args) {
        LlmAgent customerService = LlmAgent.builder()
            .name("customer_service_rep")
            .description("CloudServe customer service rep handling accounts, billing, plans, and support tickets.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a customer service representative for CloudServe Inc.
                Help customers with account inquiries, billing questions, plan changes,
                and support tickets. Always verify the account exists before making changes.
                Be professional and empathetic.
                """)
            .tools(
                FunctionTool.create(Example16CustomerService.class, "getAccountDetails"),
                FunctionTool.create(Example16CustomerService.class, "getBillingHistory"),
                FunctionTool.create(Example16CustomerService.class, "submitSupportTicket"),
                FunctionTool.create(Example16CustomerService.class, "updateAccountPlan"))
            .build();

        AgentResult result = Agentspan.run(customerService,
            "I'm customer ACC-001. Can you check my billing history and tell me my current plan? "
            + "I'm thinking about downgrading to the basic plan.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
