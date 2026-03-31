// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentHandle;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 32 — Human Guardrail (compliance review via HITL)
 *
 * <p>Demonstrates an output guardrail with {@link OnFail#HUMAN}: when the
 * agent's response contains regulated financial language the workflow pauses
 * and waits for a human compliance officer to approve or reject it before
 * the response is delivered to the end-user.
 *
 * <p>The guardrail checks for phrases that could constitute investment advice
 * or misrepresent financial risk ({@code "investment advice"},
 * {@code "guaranteed returns"}, {@code "risk-free"}). If any are present the
 * workflow enters a human-review pause rather than retrying or raising an
 * error automatically.
 *
 * <p>This example starts the workflow and prints the workflow ID. The
 * compliance review must be completed externally via the Conductor UI.
 */
public class Example32HumanGuardrail {

    // ── Market data tool ─────────────────────────────────────────────────

    static class MarketTools {
        @Tool(
            name = "get_market_data_32",
            description = "Get current market data for a stock ticker"
        )
        public Map<String, Object> getMarketData(String ticker) {
            // Hardcoded demonstration data
            return Map.of(
                "ticker", ticker.toUpperCase(),
                "price", 185.42,
                "change", "+2.3%",
                "volume", "45.2M"
            );
        }
    }

    // ── Main ─────────────────────────────────────────────────────────────

    public static void main(String[] args) {
        // ── Tools ────────────────────────────────────────────────────────

        List<ToolDef> marketTools = ToolRegistry.fromInstance(new MarketTools());

        // ── Compliance guardrail: flag regulated financial language ───────
        // OnFail.HUMAN pauses the workflow for a human compliance officer
        // to approve or reject the output rather than retrying or raising.

        GuardrailDef complianceGuardrail = GuardrailDef.builder()
            .name("compliance_review")
            .position(Position.OUTPUT)
            .onFail(OnFail.HUMAN)
            .func(content -> {
                String lower = content.toLowerCase();
                if (lower.contains("investment advice")) {
                    return GuardrailResult.fail(
                        "Output contains regulated phrase: 'investment advice'. "
                        + "Human compliance review required.");
                }
                if (lower.contains("guaranteed returns")) {
                    return GuardrailResult.fail(
                        "Output contains regulated phrase: 'guaranteed returns'. "
                        + "Human compliance review required.");
                }
                if (lower.contains("risk-free")) {
                    return GuardrailResult.fail(
                        "Output contains regulated phrase: 'risk-free'. "
                        + "Human compliance review required.");
                }
                return GuardrailResult.pass();
            })
            .build();

        // ── Finance agent ────────────────────────────────────────────────

        Agent financeAgent = Agent.builder()
            .name("finance_agent_32")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a financial information assistant. Provide market data "
                + "and general financial information. You may discuss investment "
                + "strategies and returns.")
            .tools(marketTools)
            .guardrails(List.of(complianceGuardrail))
            .build();

        // ── Start the workflow (fire-and-forget) ─────────────────────────
        // The compliance guardrail may pause the workflow for human review.
        // We start async so this process does not block.

        AgentHandle handle = Agentspan.start(financeAgent,
            "What is the current price of AAPL and is it a good risk-free investment?");

        System.out.println("Finance agent workflow started.");
        System.out.println("Workflow ID: " + handle.getWorkflowId());
        System.out.println();
        System.out.println(
            "Workflow paused for human review — the compliance guardrail flagged "
            + "the output. Approve/reject in the Conductor UI.");

        Agentspan.shutdown();
    }
}
