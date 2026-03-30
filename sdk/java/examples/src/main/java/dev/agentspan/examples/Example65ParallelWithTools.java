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
 * Example 65 — Parallel Agents with Tools (each branch has its own tools)
 *
 * <p>Extends the basic parallel pattern (Example 07) by giving each parallel
 * branch its own domain tools. All branches run concurrently and each
 * independently calls its tools.
 *
 * <pre>
 * parallel_analysis (PARALLEL)
 * ├── financial_analyst  (tools: [check_balance])
 * └── order_analyst      (tools: [lookup_order])
 * </pre>
 *
 * Both analysts run at the same time on the same input.
 */
public class Example65ParallelWithTools {

    static class FinancialTools {
        @Tool(name = "check_balance_65", description = "Check the balance of a bank account")
        public Map<String, Object> checkBalance(String accountId) {
            return Map.of(
                "account_id", accountId,
                "balance", 5432.10,
                "currency", "USD"
            );
        }
    }

    static class OrderTools {
        @Tool(name = "lookup_order_65", description = "Look up the status of an order")
        public Map<String, Object> lookupOrder(String orderId) {
            return Map.of(
                "order_id", orderId,
                "status", "shipped",
                "eta", "2 days"
            );
        }
    }

    public static void main(String[] args) {
        List<ToolDef> financialTools = ToolRegistry.fromInstance(new FinancialTools());
        List<ToolDef> orderTools = ToolRegistry.fromInstance(new OrderTools());

        Agent financialAnalyst = Agent.builder()
            .name("financial_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a financial analyst. Use check_balance_65 to look up the "
                + "account mentioned. Report the balance and any financial observations.")
            .tools(financialTools)
            .build();

        Agent orderAnalyst = Agent.builder()
            .name("order_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an order analyst. Use lookup_order_65 to check the order "
                + "mentioned. Report the status and delivery timeline.")
            .tools(orderTools)
            .build();

        // Both analysts run concurrently
        Agent analysis = Agent.builder()
            .name("parallel_analysis")
            .model(Settings.LLM_MODEL)
            .instructions("Run both analysts concurrently on the input.")
            .agents(financialAnalyst, orderAnalyst)
            .strategy(Strategy.PARALLEL)
            .build();

        AgentResult result = Agentspan.run(analysis,
            "Check account ACC-200 balance and look up order ORD-300 status.");
        result.printResult();

        Agentspan.shutdown();
    }
}
