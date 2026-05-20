// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.annotations.Tool;
import ai.agentspan.enums.EventType;
import ai.agentspan.enums.Strategy;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentEvent;
import ai.agentspan.model.AgentStream;
import ai.agentspan.model.ToolDef;

import java.util.List;

/**
 * Example 09b — Human-in-the-Loop under {@link Strategy#HANDOFF}.
 *
 * <p>The orchestrator agent ({@code support}) doesn't own any approval-required
 * tools; it routes database work to a sub-agent ({@code dba}) whose tool
 * requires approval. The HUMAN approval task therefore lives inside the
 * {@code dba} sub-workflow, not the orchestrator's workflow.
 *
 * <p>The {@code WAITING} SSE event from the sub-workflow carries that
 * sub-workflow's id in its {@code executionId} field; the SDK uses it to POST
 * {@code /api/agent/{executionId}/respond} when {@link AgentStream#approve()}
 * is called. No manual task-tree walking required from the user.
 *
 * <p>Run against a server with an LLM provider configured (e.g. {@code
 * OPENAI_API_KEY}). Expected outcome: the workflow reaches the WAITING state,
 * {@code approve()} succeeds, and the workflow runs to completion.
 */
public class Example09bHandoffHumanInTheLoop {

    static class DatabaseTools {
        @Tool(
            name = "execute_sql",
            description = "Execute a SQL statement that modifies the database",
            approvalRequired = true
        )
        public String executeSql(String statement) {
            return "Statement executed.";
        }
    }

    public static void main(String[] args) throws Exception {
        List<ToolDef> dbTools = ToolRegistry.fromInstance(new DatabaseTools());

        Agent dba = Agent.builder()
            .name("dba")
            .model(Settings.LLM_MODEL)
            .instructions("You run database statements. Use execute_sql when asked.")
            .tools(dbTools)
            .build();

        Agent support = Agent.builder()
            .name("support")
            .model(Settings.LLM_MODEL)
            .instructions("Route any database task to the dba sub-agent.")
            .agents(dba)
            .strategy(Strategy.HANDOFF)
            .build();

        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentStream stream = runtime.stream(support,
                "Please run: UPDATE users SET active = true WHERE id = 1");

            String topExecutionId = stream.getExecutionId();
            System.out.println("Top-level execution id: " + topExecutionId);

            for (AgentEvent event : stream) {
                EventType type = event.getType();
                if (type == EventType.HANDOFF) {
                    System.out.println("[HANDOFF] → " + event.getTarget());
                } else if (type == EventType.TOOL_CALL) {
                    System.out.println("[TOOL_CALL] " + event.getToolName()
                        + " " + event.getArgs());
                } else if (type == EventType.WAITING) {
                    // event.executionId is the SUB-execution id when the HUMAN task lives
                    // in a sub-agent (handoff/sequential/parallel). Pass the event to
                    // approve() so the SDK POSTs /respond to the right execution.
                    // (stream.approve() with no args targets the top-level execution and
                    // would 500 here.)
                    System.out.println("[WAITING] event.executionId=" + event.getExecutionId()
                        + " (the sub-execution that owns the HUMAN task)");
                    System.out.println("          stream.executionId=" + topExecutionId
                        + " (top-level orchestrator — approve() with no args would 500 here)");
                    System.out.println("Calling stream.approve(event)...");
                    stream.approve(event);
                    System.out.println("Approved — workflow resumes.");
                } else if (type == EventType.DONE) {
                    System.out.println("[DONE] " + event.getOutput());
                }
            }
        }
    }
}
