// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.AgentTool;
import ai.agentspan.Agentspan;
import ai.agentspan.annotations.Tool;
import ai.agentspan.internal.ToolRegistry;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 45 — Agent Tool
 *
 * <p>Demonstrates wrapping an {@link Agent} as a callable tool via
 * {@link AgentTool#from(Agent)}. Unlike sub-agents which use handoff
 * delegation, an agent_tool is invoked inline by the parent LLM — like
 * a function call. The child agent runs its own workflow and returns the
 * result as a tool output.
 *
 * <pre>
 * manager (parent)
 *   tools:
 *     - AgentTool.from(researcher)   ← child agent with search tool
 *     - calculate                    ← regular tool
 * </pre>
 */
public class Example45AgentTool {

    // ── Child agent's tool ───────────────────────────────────────────────

    static class ResearchTools {
        @Tool(name = "search_knowledge_base", description = "Search the knowledge base for information on a topic")
        public Map<String, Object> searchKnowledgeBase(String query) {
            Map<String, Map<String, Object>> data = Map.of(
                "python", Map.of(
                    "summary", "Python is a high-level programming language.",
                    "use_cases", List.of("web development", "data science", "automation")
                ),
                "rust", Map.of(
                    "summary", "Rust is a systems language focused on safety and performance.",
                    "use_cases", List.of("systems programming", "WebAssembly", "CLI tools")
                )
            );
            String key = query.toLowerCase();
            for (Map.Entry<String, Map<String, Object>> e : data.entrySet()) {
                if (key.contains(e.getKey())) {
                    Map<String, Object> result = new java.util.LinkedHashMap<>();
                    result.put("query", query);
                    result.putAll(e.getValue());
                    return result;
                }
            }
            return Map.of("query", query, "summary", "No specific data found.");
        }
    }

    // ── Parent agent's regular tool ──────────────────────────────────────

    static class MathTools {
        @Tool(name = "calculate_45", description = "Evaluate a simple math expression (digits and +-*/ only)")
        public Map<String, Object> calculate(String expression) {
            // Safe eval: only digits and basic operators
            if (!expression.matches("[0-9+\\-*/().\\s]+")) {
                return Map.of("error", "Invalid expression");
            }
            try {
                // Simple recursive descent for +/- of terms
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
        // Child agent with its own search tool
        List<ToolDef> researchTools = ToolRegistry.fromInstance(new ResearchTools());
        Agent researcher = Agent.builder()
            .name("researcher_45")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a research assistant. Use search_knowledge_base to find "
                + "information about topics. Provide concise summaries.")
            .tools(researchTools)
            .build();

        // Parent agent: researcher wrapped as agent_tool + regular calculate tool
        List<ToolDef> mathTools = ToolRegistry.fromInstance(new MathTools());
        Agent manager = Agent.builder()
            .name("manager_45")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a project manager. Use the researcher_45 tool to gather "
                + "information and the calculate_45 tool for math. Synthesize findings.")
            .tools(List.of(AgentTool.from(researcher), mathTools.get(0)))
            .build();

        AgentResult result = Agentspan.run(manager,
            "Research Python and Rust, then calculate how many use cases they have combined.");
        result.printResult();

        Agentspan.shutdown();
    }
}
