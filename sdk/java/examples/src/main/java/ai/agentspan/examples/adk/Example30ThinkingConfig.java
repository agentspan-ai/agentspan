// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.Map;

/**
 * Example Adk 30 — Thinking Config
 *
 * <p>Java port of <code>sdk/python/examples/adk/30_thinking_config.py</code>.
 *
 * <p>Demonstrates: ADK's extended thinking mode via
 * {@code ThinkingConfig(thinking_budget=2048)}. The Java {@link GoogleADKAgent}
 * builder does not expose thinking_config directly; we encode the
 * step-by-step reasoning intent in the agent instruction.
 */
public class Example30ThinkingConfig {

    static class CalcTools {

        @Tool(name = "calculate", value = "Evaluate a mathematical expression.")
        public Map<String, Object> calculate(@P("expression") String expression) {
            // Safe-only digits + basic operators evaluator.
            if (!expression.matches("[0-9+\\-*/().\\s]+")) {
                return Map.of("expression", expression, "error", "Invalid expression");
            }
            try {
                double result = evalExpr(expression.replaceAll("\\s+", ""), new int[]{0});
                return Map.of("expression", expression, "result", result);
            } catch (Exception e) {
                return Map.of("expression", expression, "error", e.getMessage());
            }
        }

        private double evalExpr(String s, int[] pos) {
            double val = evalTerm(s, pos);
            while (pos[0] < s.length() && (s.charAt(pos[0]) == '+' || s.charAt(pos[0]) == '-')) {
                char op = s.charAt(pos[0]++);
                val = op == '+' ? val + evalTerm(s, pos) : val - evalTerm(s, pos);
            }
            return val;
        }

        private double evalTerm(String s, int[] pos) {
            double val = evalFactor(s, pos);
            while (pos[0] < s.length() && (s.charAt(pos[0]) == '*' || s.charAt(pos[0]) == '/')) {
                char op = s.charAt(pos[0]++);
                val = op == '*' ? val * evalFactor(s, pos) : val / evalFactor(s, pos);
            }
            return val;
        }

        private double evalFactor(String s, int[] pos) {
            if (pos[0] < s.length() && s.charAt(pos[0]) == '(') {
                pos[0]++;
                double val = evalExpr(s, pos);
                pos[0]++; // ')'
                return val;
            }
            int start = pos[0];
            while (pos[0] < s.length() && (Character.isDigit(s.charAt(pos[0])) || s.charAt(pos[0]) == '.')) pos[0]++;
            return Double.parseDouble(s.substring(start, pos[0]));
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("deep_thinker")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an analytical assistant. Think carefully through complex "
                + "problems step by step. Use the calculate tool for math.")
            .tools(new CalcTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "If a train travels 120 km in 2 hours, then speeds up by 50% for "
            + "the next 3 hours, what is the total distance traveled?");
        result.printResult();

        Agentspan.shutdown();
    }
}
