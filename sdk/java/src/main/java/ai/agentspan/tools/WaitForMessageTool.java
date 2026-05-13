// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.tools;

import ai.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Factory for a tool that dequeues messages from the Workflow Message Queue
 * (Conductor {@code PULL_WORKFLOW_MESSAGES} task).
 *
 * <p>No worker process is needed. In blocking mode (default) the task waits until at least
 * one message arrives. In non-blocking mode it returns immediately.
 *
 * <pre>{@code
 * ToolDef listen = WaitForMessageTool.create(
 *     "wait_for_message", "Wait until a message is sent to this agent.");
 *
 * // Non-blocking (returns immediately if queue is empty):
 * ToolDef poll = WaitForMessageTool.create("poll_messages", "Poll for messages.", 5, false);
 * }</pre>
 */
public class WaitForMessageTool {

    private WaitForMessageTool() {}

    /** Create a blocking, single-message wait tool. */
    public static ToolDef create(String name, String description) {
        return create(name, description, 1, true);
    }

    /**
     * Create a message-wait tool.
     *
     * @param name       tool name shown to the LLM
     * @param description tool description shown to the LLM
     * @param batchSize  maximum number of messages to dequeue per invocation (server cap: 100)
     * @param blocking   if true, waits until at least one message is available
     */
    public static ToolDef create(String name, String description, int batchSize, boolean blocking) {
        Map<String, Object> config = new LinkedHashMap<>();
        config.put("batchSize", batchSize);
        if (!blocking) {
            config.put("blocking", false);
        }
        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", new LinkedHashMap<>());
        return ToolDef.builder()
                .name(name)
                .description(description)
                .inputSchema(inputSchema)
                .toolType("pull_workflow_messages")
                .config(config)
                .build();
    }
}
