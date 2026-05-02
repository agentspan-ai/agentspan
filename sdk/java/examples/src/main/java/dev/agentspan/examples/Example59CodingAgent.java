// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;

import java.util.List;

/**
 * Example 59 — Coding Agent with Local Code Execution
 *
 * <p>Demonstrates a coder/QA swarm where one agent writes Python code and
 * another executes it locally to verify correctness.
 *
 * <pre>
 * swarm_lead (SWARM)
 *   ├── coder_agent   — writes Python code
 *   └── qa_agent      — executes code, reports failures
 * </pre>
 *
 * <p>The {@code localCodeExecution(true)} flag registers an
 * {@code {agent_name}_execute_code} Conductor worker that spawns a real
 * subprocess on the SDK host machine.
 */
public class Example59CodingAgent {

    public static void main(String[] args) {
        // ── QA agent: receives code from coder, runs it ──────────────────────

        Agent qaAgent = Agent.builder()
            .name("qa_agent_59")
            .model(Settings.LLM_MODEL)
            .localCodeExecution(true)
            .allowedLanguages(List.of("python"))
            .codeExecutionTimeout(20)
            .instructions(
                "You are a QA engineer. When given Python code to test:\n" +
                "1. Call qa_agent_59_execute_code with the code and language='python'\n" +
                "2. Check exit_code and output\n" +
                "3. Report PASS if exit_code==0 and output is correct, FAIL with details otherwise.")
            .build();

        // ── Coder agent: writes the code ─────────────────────────────────────

        Agent coderAgent = Agent.builder()
            .name("coder_agent_59")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an expert Python developer. Write clean, correct Python code " +
                "that solves the given problem. Output ONLY the Python code, no markdown fences.")
            .build();

        // ── Swarm lead: orchestrates coder → QA ──────────────────────────────

        Agent swarmLead = Agent.builder()
            .name("coding_swarm_59")
            .model(Settings.LLM_MODEL)
            .agents(coderAgent, qaAgent)
            .strategy(Strategy.SWARM)
            .maxTurns(8)
            .instructions(
                "You coordinate a coding team. For each task:\n" +
                "1. Ask coder_agent_59 to write the solution code\n" +
                "2. Pass the code to qa_agent_59 to execute and verify\n" +
                "3. If QA reports FAIL, ask coder_agent_59 to fix and repeat\n" +
                "4. Once QA reports PASS, present the final solution and test output.")
            .build();

        System.out.println("=== Coding Agent: Fibonacci + Palindrome Check ===");
        AgentResult result = Agentspan.run(swarmLead,
            "Write and test Python code that:\n" +
            "1. Computes the first 10 Fibonacci numbers\n" +
            "2. Checks which of those numbers are palindromes when written as strings\n" +
            "3. Prints both lists");
        result.printResult();

        Agentspan.shutdown();
    }
}
