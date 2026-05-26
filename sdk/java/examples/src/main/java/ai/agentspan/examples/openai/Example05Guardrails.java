// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example OpenAi 05 — Guardrails
 *
 * <p>Java port of <code>sdk/python/examples/openai/05_guardrails.py</code>.
 *
 * <p>Demonstrates: a banking assistant that uses function tools to look up
 * balances and transfer funds. The Python original wraps the agent with
 * input + output guardrails (PII regex on input, forbidden-phrase scan on
 * output).
 *
 * <p>Python parity gap: the current {@link OpenAIAgent} builder does not
 * expose {@code input_guardrails} / {@code output_guardrails}. The generic
 * {@code Agent.Builder} has a {@code .guardrails(...)} hook but it is not
 * surfaced on the OpenAIAgent factory. We port the tool surface and agent
 * shape faithfully; the guardrail wrappers are described here for parity
 * but not wired:
 * <ul>
 *   <li>Input guardrail: reject messages containing an SSN regex
 *       ({@code \b\d{3}-\d{2}-\d{4}\b}) or a credit-card regex
 *       ({@code \b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b}).</li>
 *   <li>Output guardrail: reject responses mentioning any of
 *       "internal system", "database password", "api key", "secret token".</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example05Guardrails {

    static class BankingTools {

        @Tool(name = "get_account_balance", description = "Look up the balance of a bank account.")
        public String getAccountBalance(String account_id) {
            switch (account_id) {
                case "ACC-100": return "$5,230.00";
                case "ACC-200": return "$12,750.50";
                case "ACC-300": return "$890.25";
                default: return "Account " + account_id + " not found";
            }
        }

        @Tool(name = "transfer_funds", description = "Transfer funds between accounts.")
        public String transferFunds(String from_account, String to_account, double amount) {
            return String.format("Transferred $%.2f from %s to %s.", amount, from_account, to_account);
        }
    }

    public static void main(String[] args) {
        Agent agent = OpenAIAgent.builder()
                .name("banking_assistant")
                .instructions(
                        "You are a secure banking assistant. Help users check account balances "
                                + "and transfer funds. Never reveal internal system details.")
                .model(Settings.LLM_MODEL)
                .tools(new BankingTools())
                .build();

        // This should pass guardrails (no PII, no forbidden phrases in response).
        AgentResult result = Agentspan.run(agent, "What's the balance on account ACC-100?");
        result.printResult();

        Agentspan.shutdown();
    }
}
