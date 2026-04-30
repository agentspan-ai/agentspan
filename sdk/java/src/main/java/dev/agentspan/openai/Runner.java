// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.openai;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;

import java.util.concurrent.CompletableFuture;

/**
 * OpenAI Agents SDK compatible runner — drop-in replacement for {@code openai-agents} Runner.
 *
 * <p>Change one import line:
 * <pre>
 * // Before: import com.openai.agents.Runner;
 * // After:
 * import dev.agentspan.openai.Runner;
 * </pre>
 *
 * <p>Your agents now run on Agentspan instead of directly against OpenAI,
 * gaining durability, observability, and horizontal scaling.
 *
 * <pre>{@code
 * RunResult result = Runner.runSync(agent, "What's the weather in NYC?");
 * System.out.println(result.getFinalOutput());
 * }</pre>
 */
public class Runner {

    private Runner() {}

    /**
     * Run an agent synchronously and return the result.
     *
     * @param agent  the agent to run (Agentspan or openai-agents compatible)
     * @param prompt the user's input message
     * @return a RunResult with the final output
     */
    public static RunResult runSync(Agent agent, String prompt) {
        try (AgentRuntime runtime = new AgentRuntime()) {
            return new RunResult(runtime.run(agent, prompt));
        }
    }

    /**
     * Run an agent asynchronously.
     *
     * @param agent  the agent to run
     * @param prompt the user's input message
     * @return a CompletableFuture that resolves to a RunResult
     */
    public static CompletableFuture<RunResult> run(Agent agent, String prompt) {
        AgentRuntime runtime = new AgentRuntime();
        return runtime.runAsync(agent, prompt)
            .thenApply(RunResult::new)
            .whenComplete((r, t) -> runtime.close());
    }
}
