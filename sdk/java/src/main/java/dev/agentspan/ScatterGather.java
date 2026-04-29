// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.model.ToolDef;
import java.util.ArrayList;
import java.util.List;

/**
 * Factory for the scatter-gather multi-agent pattern.
 *
 * <p>Creates a coordinator agent that decomposes a problem into N independent
 * sub-tasks, dispatches the worker agent N times in parallel (via
 * {@link AgentTool}), and synthesizes the results.
 *
 * <p>Example:
 * <pre>{@code
 * Agent researcher = Agent.builder()
 *     .name("researcher")
 *     .model("openai/gpt-4o")
 *     .instructions("Research a given topic and return key findings.")
 *     .tools(searchTools)
 *     .build();
 *
 * Agent coordinator = ScatterGather.create("coordinator", researcher,
 *     "openai/gpt-4o",
 *     "Analyze each topic independently, then produce a comparative report.",
 *     300);
 *
 * AgentResult result = Agentspan.run(coordinator, "Compare Python, Rust, and Go for CLI tools.");
 * }</pre>
 */
public class ScatterGather {

    private static final String INSTRUCTIONS_PREFIX =
        "You are a scatter-gather coordinator. Your job is to:\n" +
        "1. Decompose the input into N independent sub-problems\n" +
        "2. Call the '%s' tool MULTIPLE TIMES IN PARALLEL — once per sub-problem, " +
        "each with a clear, self-contained prompt\n" +
        "3. After all results return, synthesize them into a unified answer\n\n" +
        "IMPORTANT: Issue all '%s' tool calls in a SINGLE response to maximize parallelism.\n\n";

    private ScatterGather() {}

    /**
     * Create a scatter-gather coordinator agent.
     *
     * @param name         name for the coordinator agent
     * @param worker       the worker agent to dispatch for each sub-task
     * @param model        LLM model for the coordinator
     * @param instructions additional instructions appended after auto-generated prefix
     * @param timeoutSeconds server-side timeout in seconds (default 300 if 0)
     * @return a coordinator Agent configured for scatter-gather
     */
    public static Agent create(String name, Agent worker, String model,
                               String instructions, int timeoutSeconds) {
        String workerName = worker.getName();
        String prefix = String.format(INSTRUCTIONS_PREFIX, workerName, workerName);
        String fullInstructions = instructions != null && !instructions.isEmpty()
                ? prefix + instructions
                : prefix.trim();

        int timeout = timeoutSeconds > 0 ? timeoutSeconds : 300;

        List<ToolDef> tools = new ArrayList<>();
        tools.add(AgentTool.from(worker));

        return Agent.builder()
                .name(name)
                .model(model)
                .instructions(fullInstructions)
                .tools(tools)
                .timeoutSeconds(timeout)
                .build();
    }

    /**
     * Create a scatter-gather coordinator with default 5-minute timeout.
     */
    public static Agent create(String name, Agent worker, String model, String instructions) {
        return create(name, worker, model, instructions, 300);
    }

    /**
     * Create a scatter-gather coordinator using the worker's model.
     */
    public static Agent create(String name, Agent worker, String instructions) {
        return create(name, worker, worker.getModel(), instructions, 300);
    }
}
