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
import java.util.Scanner;

/**
 * Example 09 — Human-in-the-Loop
 *
 * <p>Demonstrates tools that require human approval before execution.
 * Uses {@link Tool#approvalRequired()} and streaming to intercept WAITING events.
 */
public class Example09HumanInTheLoop {

    static class DatabaseTools {
        @Tool(
            name = "execute_sql",
            description = "Execute a SQL query on the production database",
            approvalRequired = true  // Requires human approval
        )
        public String executeSql(String query) {
            // In a real app, this would execute the SQL
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

        Scanner scanner = new Scanner(System.in);

        try (AgentRuntime runtime = new AgentRuntime()) {
            AgentStream stream = runtime.stream(agent,
                "Please update all users with 'inactive' status to 'active' and confirm the count.");

            System.out.println("\nStreaming agent events (press Enter to approve/reject tools):\n");

            for (AgentEvent event : stream) {
                EventType type = event.getType();

                if (type == EventType.THINKING) {
                    System.out.println("[THINKING] " + event.getContent());
                } else if (type == EventType.TOOL_CALL) {
                    System.out.println("[TOOL_CALL] " + event.getToolName()
                        + " args: " + event.getArgs());
                } else if (type == EventType.WAITING) {
                    System.out.println("\n[WAITING] Tool '" + event.getToolName()
                        + "' requires approval!");
                    System.out.print("Approve? (y/n): ");

                    String input = scanner.nextLine().trim().toLowerCase();
                    if ("y".equals(input)) {
                        System.out.println("Approving...");
                        stream.approve();
                    } else {
                        System.out.print("Rejection reason: ");
                        String reason = scanner.nextLine().trim();
                        stream.reject(reason.isEmpty() ? "Rejected by user" : reason);
                    }
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
