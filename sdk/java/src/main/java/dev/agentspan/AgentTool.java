// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import dev.agentspan.internal.AgentConfigSerializer;
import dev.agentspan.model.ToolDef;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Factory for wrapping an {@link Agent} as a callable tool (agent_tool).
 *
 * <p>Unlike sub-agents which use handoff delegation, an agent_tool is invoked
 * inline by the parent LLM like a function call. The child agent runs its own
 * workflow and returns the result as a tool output.
 *
 * <pre>{@code
 * Agent researcher = Agent.builder()
 *     .name("researcher")
 *     .model("openai/gpt-4o-mini")
 *     .tools(searchTools)
 *     .instructions("Research topics and provide summaries.")
 *     .build();
 *
 * Agent manager = Agent.builder()
 *     .name("manager")
 *     .model("openai/gpt-4o-mini")
 *     .tools(List.of(AgentTool.from(researcher), calculateTool))
 *     .instructions("Delegate research tasks and synthesize results.")
 *     .build();
 * }</pre>
 */
public class AgentTool {

    private AgentTool() {}

    /**
     * Wrap an agent as a callable tool with default description.
     *
     * @param agent the agent to wrap
     * @return a ToolDef with {@code toolType="agent_tool"}
     */
    public static ToolDef from(Agent agent) {
        return from(agent, "Invoke the " + agent.getName() + " agent");
    }

    /**
     * Wrap an agent as a callable tool with a custom description.
     *
     * @param agent       the agent to wrap
     * @param description what this tool does (shown to the LLM)
     * @return a ToolDef with {@code toolType="agent_tool"}
     */
    public static ToolDef from(Agent agent, String description) {
        Map<String, Object> agentConfig = new AgentConfigSerializer().serialize(agent);

        Map<String, Object> config = new LinkedHashMap<>();
        config.put("agentConfig", agentConfig);

        Map<String, Object> inputSchema = Map.of(
            "type", "object",
            "properties", Map.of(
                "request", Map.of(
                    "type", "string",
                    "description", "The request or question to send to this agent."
                )
            ),
            "required", List.of("request")
        );

        return ToolDef.builder()
            .name(agent.getName())
            .description(description)
            .toolType("agent_tool")
            .inputSchema(inputSchema)
            .config(config)
            .agentRef(agent)
            .build();
    }
}
