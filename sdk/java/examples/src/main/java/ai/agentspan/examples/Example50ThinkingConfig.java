// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 50 — Thinking Config (extended reasoning)
 *
 * <p>When {@code thinkingBudgetTokens} is set, the agent uses extended
 * thinking mode, allowing the LLM to reason step-by-step before responding.
 * This improves performance on complex analytical tasks at the cost of
 * higher token usage.
 *
 * <p>Only supported by models with extended thinking capability
 * (e.g., Claude with thinking mode).
 */
public class Example50ThinkingConfig {

    static class MathTools {
        @Tool(name = "calculate_50", description = "Evaluate a mathematical expression safely")
        public Map<String, Object> calculate(String expression) {
            try {
                javax.script.ScriptEngineManager mgr = new javax.script.ScriptEngineManager();
                javax.script.ScriptEngine engine = mgr.getEngineByName("js");
                Object result = engine.eval(expression);
                return Map.of("expression", expression, "result", result);
            } catch (Exception e) {
                return Map.of("expression", expression, "error", e.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        List<ToolDef> tools = ToolRegistry.fromInstance(new MathTools());

        Agent agent = Agent.builder()
            .name("deep_thinker_50")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an analytical assistant. Think carefully through complex "
                + "problems step by step. Use the calculate_50 tool for math.")
            .tools(tools)
            .thinkingBudgetTokens(2048)
            .build();

        AgentResult result = Agentspan.run(agent,
            "If a train travels 120 km in 2 hours, then speeds up by 50% for "
            + "the next 3 hours, what is the total distance traveled?");
        result.printResult();

        Agentspan.shutdown();
    }
}
