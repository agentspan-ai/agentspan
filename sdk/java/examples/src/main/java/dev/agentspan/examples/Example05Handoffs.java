// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.Strategy;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 05 — Multi-Agent Handoffs
 *
 * <p>Demonstrates multi-agent orchestration with handoff strategy.
 * The orchestrator LLM decides which specialist sub-agent to invoke.
 */
public class Example05Handoffs {

    static class BillingTools {
        @Tool(name = "check_balance", description = "Check the balance of a bank account")
        public Map<String, Object> checkBalance(String accountId) {
            return Map.of("account_id", accountId, "balance", 5432.10, "currency", "USD");
        }
    }

    static class TechnicalTools {
        @Tool(name = "lookup_order", description = "Look up the status of an order")
        public Map<String, Object> lookupOrder(String orderId) {
            return Map.of("order_id", orderId, "status", "shipped", "eta", "2 days");
        }
    }

    static class SalesTools {
        @Tool(name = "get_pricing", description = "Get pricing information for a product")
        public Map<String, Object> getPricing(String product) {
            return Map.of("product", product, "price", 99.99, "discount", "10% off");
        }
    }

    public static void main(String[] args) {
        List<ToolDef> billingTools = ToolRegistry.fromInstance(new BillingTools());
        List<ToolDef> technicalTools = ToolRegistry.fromInstance(new TechnicalTools());
        List<ToolDef> salesTools = ToolRegistry.fromInstance(new SalesTools());

        // Specialist agents with domain tools
        Agent billingAgent = Agent.builder()
            .name("billing")
            .model(Settings.LLM_MODEL)
            .instructions("You handle billing questions: balances, payments, invoices.")
            .tools(billingTools)
            .build();

        Agent technicalAgent = Agent.builder()
            .name("technical")
            .model(Settings.LLM_MODEL)
            .instructions("You handle technical questions: order status, shipping, returns.")
            .tools(technicalTools)
            .build();

        Agent salesAgent = Agent.builder()
            .name("sales")
            .model(Settings.LLM_MODEL)
            .instructions("You handle sales questions: pricing, products, promotions.")
            .tools(salesTools)
            .build();

        // Orchestrator with handoff strategy
        Agent support = Agent.builder()
            .name("support")
            .model(Settings.LLM_MODEL)
            .instructions("Route customer requests to the right specialist: billing, technical, or sales.")
            .agents(billingAgent, technicalAgent, salesAgent)
            .strategy(Strategy.HANDOFF)
            .build();

        AgentResult result = Agentspan.run(support, "What's the balance on account ACC-123?");
        result.printResult();

        Agentspan.shutdown();
    }
}
