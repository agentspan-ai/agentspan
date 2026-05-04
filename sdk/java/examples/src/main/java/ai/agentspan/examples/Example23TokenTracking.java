// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.model.TokenUsage;

import java.util.List;
import java.util.Map;

/**
 * Example 23 — Token and Cost Tracking
 *
 * <p>Demonstrates the {@code TokenUsage} field on {@link AgentResult}, which
 * provides aggregated token usage across all LLM calls in an agent execution.
 *
 * <p>Use token counts to:
 * <ul>
 *   <li>Monitor costs and usage patterns</li>
 *   <li>Enforce budget limits</li>
 *   <li>Compare efficiency across agent designs</li>
 * </ul>
 */
public class Example23TokenTracking {

    static class MathTools {
        @Tool(name = "calculate", description = "Evaluate a mathematical expression")
        public String calculate(String expression) {
            try {
                javax.script.ScriptEngineManager mgr = new javax.script.ScriptEngineManager();
                javax.script.ScriptEngine engine = mgr.getEngineByName("js");
                Object result = engine.eval(expression);
                return String.valueOf(result);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new MathTools());

        Agent agent = Agent.builder()
            .name("math_tutor")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You are a math tutor. Solve problems step by step, using the calculate "
                + "tool for computations. Explain each step clearly.")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Calculate the compound interest on $10,000 at 5% annual rate "
            + "compounded monthly for 3 years.");
        result.printResult();

        // ── Token usage summary ─────────────────────────────────────────────

        TokenUsage usage = result.getTokenUsage();
        if (usage != null) {
            System.out.println("=== Token Usage Summary ===");
            System.out.printf("  Prompt tokens:     %d%n", usage.getPromptTokens());
            System.out.printf("  Completion tokens: %d%n", usage.getCompletionTokens());
            System.out.printf("  Total tokens:      %d%n", usage.getTotalTokens());

            // Estimate cost (example pricing for gpt-4o-mini)
            double promptCost = usage.getPromptTokens() * 0.00015 / 1000;
            double completionCost = usage.getCompletionTokens() * 0.00060 / 1000;
            System.out.printf("  Estimated cost:    $%.6f (prompt) + $%.6f (completion)%n",
                promptCost, completionCost);
        } else {
            System.out.println("Token usage not available from server.");
        }

        Agentspan.shutdown();
    }
}
