// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.enums.OnFail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.AgentHandle;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.GuardrailResult;
import org.conductoross.conductor.ai.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 32 — Human Guardrail (compliance review, auto-approved)
 *
 * <p>Demonstrates an output guardrail with {@link OnFail#HUMAN}: when the
 * agent's response contains regulated financial language the workflow pauses
 * for human compliance review. In this example the review is auto-approved
 * programmatically to make the example fully runnable end-to-end.
 *
 * <p>In a real application, a compliance officer would review the output in
 * the Conductor UI or via {@code handle.approve()} / {@code handle.reject()}
 * before the response is delivered to the end-user.
 */
public class Example32HumanGuardrail {

    static class MarketTools {
        @Tool(
            name = "get_market_data_32",
            description = "Get current market data for a stock ticker"
        )
        public Map<String, Object> getMarketData(String ticker) {
            return Map.of(
                "ticker", ticker.toUpperCase(),
                "price", 185.42,
                "change", "+2.3%",
                "volume", "45.2M"
            );
        }
    }

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        List<ToolDef> marketTools = ToolRegistry.fromInstance(new MarketTools());

        // Guardrail: flag regulated financial language — pause for human review on fail
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

        // Start async — the compliance guardrail may pause the workflow
        AgentHandle handle = runtime.start(financeAgent,
            "What is the current price of AAPL and is it a good risk-free investment?");

        System.out.println("Execution ID: " + handle.getExecutionId());
        System.out.println("Waiting for compliance guardrail review...");

        // Poll for the WAITING state; auto-approve to simulate human approval
        boolean paused = handle.waitUntilWaiting(60_000);
        if (paused) {
            System.out.println("Guardrail triggered — auto-approving (simulating compliance officer).");
            handle.approve();
        } else {
            System.out.println("Workflow completed without guardrail pause (output was compliant).");
        }

        AgentResult result = handle.waitForResult();
        result.printResult();

        runtime.shutdown();
    }
}
