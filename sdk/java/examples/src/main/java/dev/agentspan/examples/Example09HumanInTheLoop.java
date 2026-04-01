// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.AgentRuntime;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.EventType;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentEvent;
import dev.agentspan.model.AgentStream;
import dev.agentspan.model.ToolDef;

import java.util.List;

/**
 * Example 09 — Human-in-the-Loop (auto-approve simulation)
 *
 * <p>Demonstrates tools that require human approval before execution.
 * Uses {@link Tool#approvalRequired()} and streaming to intercept WAITING events.
 * In this example the approval is granted automatically — in a real application
 * a UI would present the pending tool call and wait for a human decision.
 */
public class Example09HumanInTheLoop {

    static class DatabaseTools {
        @Tool(
            name = "execute_sql",
            description = "Execute a SQL query on the production database",
            approvalRequired = true
        )
        public String executeSql(String query) {
            System.out.println("\n[DATABASE] Executing: " + query);
            return "Query executed successfully. 42 rows affected.";
        }

        @Tool(
            name = "read_sql",
            description = "Read data from the database (no approval needed)",
            approvalRequired = false
        )
        public String readSql(String query) {
            return "Result: [{id: 1, name: 'Alice'}, {id: 2, name: 'Bob'}]";
        }
    }

    public static void main(String[] args) throws Exception {
        DatabaseTools dbTools = new DatabaseTools();
        List<ToolDef> tools = ToolRegistry.fromInstance(dbTools);

        Agent agent = Agent.builder()
            .name("database_agent")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a database assistant. Help users query and modify the database. "
                + "Use read_sql for SELECT queries and execute_sql for INSERT/UPDATE/DELETE.")
            .tools(tools)
            .build();

        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentStream stream = runtime.stream(agent,
                "Please update all users with 'inactive' status to 'active' and confirm the count.");

            System.out.println("Streaming agent events (WAITING events are auto-approved):\n");

            for (AgentEvent event : stream) {
                EventType type = event.getType();

                if (type == EventType.THINKING) {
                    System.out.println("[THINKING] " + event.getContent());
                } else if (type == EventType.TOOL_CALL) {
                    System.out.println("[TOOL_CALL] " + event.getToolName()
                        + " args: " + event.getArgs());
                } else if (type == EventType.WAITING) {
                    System.out.println("[WAITING] Tool '" + event.getToolName()
                        + "' requires approval — auto-approving.");
                    stream.approve();
                } else if (type == EventType.TOOL_RESULT) {
                    System.out.println("[TOOL_RESULT] " + event.getResult());
                } else if (type == EventType.MESSAGE) {
                    System.out.println("[MESSAGE] " + event.getContent());
                } else if (type == EventType.DONE) {
                    System.out.println("[DONE] Agent completed");
                }
            }

            System.out.println("\nFinal result:");
            stream.getResult().printResult();
        }
    }
}
