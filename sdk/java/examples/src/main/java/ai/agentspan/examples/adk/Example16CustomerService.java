// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

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

    static class CsTools {

        @Tool(name = "get_account_details", value = "Retrieve account details for a customer.")
        public Map<String, Object> getAccountDetails(@P("account_id") String accountId) {
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

        @Tool(name = "get_billing_history", value = "Get billing history for an account.")
        public Map<String, Object> getBillingHistory(
                @P("account_id") String accountId,
                @P("num_months") int numMonths) {
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

        @Tool(name = "submit_support_ticket", value = "Submit a support ticket for a customer issue.")
        public Map<String, Object> submitSupportTicket(
                @P("account_id") String accountId,
                @P("category") String category,
                @P("description") String description) {
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

        @Tool(name = "update_account_plan", value = "Update the subscription plan for an account.")
        public Map<String, Object> updateAccountPlan(
                @P("account_id") String accountId,
                @P("new_plan") String newPlan) {
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
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("customer_service_rep")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a customer service representative for CloudServe Inc. "
                + "Help customers with account inquiries, billing questions, plan changes, "
                + "and support tickets. Always verify the account exists before making changes. "
                + "Be professional and empathetic.")
            .tools(new CsTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "I'm customer ACC-001. Can you check my billing history and tell me my current plan? "
            + "I'm thinking about downgrading to the basic plan.");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
