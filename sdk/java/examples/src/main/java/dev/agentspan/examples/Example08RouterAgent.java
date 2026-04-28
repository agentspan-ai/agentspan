// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

/**
 * Example 08 — Router Agent
 *
 * <p>Demonstrates the router pattern where a dedicated router LLM
 * selects which sub-agent handles each request.
 */
public class Example08RouterAgent {

    public static void main(String[] args) {
        // Specialist agents
        Agent pythonExpert = Agent.builder()
            .name("python_expert")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a Python expert. Answer Python programming questions, "
                + "provide code examples, and explain Python best practices.")
            .build();

        Agent javaExpert = Agent.builder()
            .name("java_expert")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a Java expert. Answer Java programming questions, "
                + "provide code examples, and explain Java best practices.")
            .build();

        Agent sqlExpert = Agent.builder()
            .name("sql_expert")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a SQL expert. Answer database and SQL queries, "
                + "provide query examples, and explain database optimization.")
            .build();

        // Router: decides which expert to use
        Agent router = Agent.builder()
            .name("lang_router")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a routing agent. Based on the user's question, select the most appropriate expert:\n"
                + "- 'python_expert' for Python questions\n"
                + "- 'java_expert' for Java questions\n"
                + "- 'sql_expert' for SQL/database questions\n"
                + "Respond ONLY with the agent name, nothing else.")
            .build();

        // Router strategy with explicit router
        Agent codingAssistant = Agent.builder()
            .name("coding_assistant")
            .model(Settings.LLM_MODEL)
            .instructions("Route coding questions to the appropriate expert.")
            .agents(pythonExpert, javaExpert, sqlExpert)
            .strategy(Strategy.ROUTER)
            .router(router)
            .build();

        // Test with different questions
        System.out.println("=== Python Question ===");
        AgentResult pythonResult = Agentspan.run(codingAssistant,
            "How do I use list comprehensions in Python?");
        pythonResult.printResult();

        System.out.println("=== SQL Question ===");
        AgentResult sqlResult = Agentspan.run(codingAssistant,
            "How do I write a SQL query to find the top 10 customers by revenue?");
        sqlResult.printResult();

        Agentspan.shutdown();
    }
}
