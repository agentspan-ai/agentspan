// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.model.AgentHandle;
import ai.agentspan.model.AgentResult;

/**
 * Example 12 — Long-Running Agent (fire-and-forget with polling)
 *
 * <p>Demonstrates starting an agent asynchronously and polling for its result.
 * The agent runs as a Conductor workflow and can be monitored independently.
 * In production, the workflow ID can be saved and checked from any process.
 */
public class Example12LongRunning {

    public static void main(String[] args) throws InterruptedException {
        Agent analyst = Agent.builder()
            .name("saas_analyst")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a data analyst. Provide a concise analysis "
                + "when asked about data topics.")
            .build();

        try (AgentRuntime runtime = new AgentRuntime()) {
            runtime.prepareWorkers(analyst);

            // Fire-and-forget: start returns immediately with a handle
            AgentHandle handle = runtime.start(analyst,
                "What are the key metrics to track for a SaaS product?");

            System.out.println("Agent started: " + handle.getWorkflowId());
            System.out.println("Polling for result...");

            // Simulate doing other work while the agent runs
            System.out.println("[doing other work...]");
            Thread.sleep(1000);

            // Poll for result with a 2-minute timeout, checking every 2s
            AgentResult result = handle.waitForResult(120_000, 2000);
            result.printResult();
        }
    }
}
