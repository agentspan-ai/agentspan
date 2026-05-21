// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.AgentTool;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 21 — Agent Tool
 *
 * <p>Java port of <code>sdk/python/examples/adk/21_agent_tool.py</code>.
 *
 * <p>Demonstrates: wrapping agents as callable tools via native ADK's
 * {@link AgentTool#create(com.google.adk.agents.BaseAgent)}. Unlike sub-agents
 * (handoff), an {@code AgentTool} runs inline and returns its output back to
 * the parent like a function call.
 */
public class Example21AgentTool {

    @Schema(description = "Search an internal knowledge base for information.")
    public static Map<String, Object> searchKnowledgeBase(
            @Schema(name = "query", description = "Search query") String query) {
        Map<String, Map<String, Object>> data = new LinkedHashMap<>();
        data.put("python", Map.of(
            "summary", "Python is a high-level programming language created by Guido van Rossum in 1991.",
            "popularity", "Most popular language on TIOBE index (2024)",
            "key_use_cases", List.of("web development", "data science", "AI/ML", "automation")
        ));
        data.put("rust", Map.of(
            "summary", "Rust is a systems programming language focused on safety and performance.",
            "popularity", "Most admired language on Stack Overflow survey (2024)",
            "key_use_cases", List.of("systems programming", "WebAssembly", "CLI tools", "embedded")
        ));
        String q = query.toLowerCase();
        for (Map.Entry<String, Map<String, Object>> entry : data.entrySet()) {
            if (q.contains(entry.getKey())) {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("query", query);
                r.put("found", true);
                r.putAll(entry.getValue());
                return r;
            }
        }
        return Map.of("query", query, "found", false, "summary", "No results found.");
    }

    @Schema(description = "Evaluate a mathematical expression.")
    public static Map<String, Object> compute(
            @Schema(name = "expression", description = "Math expression") String expression) {
        // Safe-only digits + basic operators evaluator
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

    private static double evalExpr(String s, int[] pos) {
        double val = evalTerm(s, pos);
        while (pos[0] < s.length() && (s.charAt(pos[0]) == '+' || s.charAt(pos[0]) == '-')) {
            char op = s.charAt(pos[0]++);
            val = op == '+' ? val + evalTerm(s, pos) : val - evalTerm(s, pos);
        }
        return val;
    }

    private static double evalTerm(String s, int[] pos) {
        double val = evalFactor(s, pos);
        while (pos[0] < s.length() && (s.charAt(pos[0]) == '*' || s.charAt(pos[0]) == '/')) {
            char op = s.charAt(pos[0]++);
            val = op == '*' ? val * evalFactor(s, pos) : val / evalFactor(s, pos);
        }
        return val;
    }

    private static double evalFactor(String s, int[] pos) {
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

    public static void main(String[] args) {
        LlmAgent researcher = LlmAgent.builder()
            .name("researcher")
            .description("Looks up factual information from the internal knowledge base.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research assistant. Use the knowledge base tool to find "
                + "information and provide concise, factual answers.")
            .tools(FunctionTool.create(Example21AgentTool.class, "searchKnowledgeBase"))
            .build();

        LlmAgent calculator = LlmAgent.builder()
            .name("calculator")
            .description("Evaluates simple math expressions with the compute tool.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a math assistant. Use the compute tool for calculations.")
            .tools(FunctionTool.create(Example21AgentTool.class, "compute"))
            .build();

        LlmAgent manager = LlmAgent.builder()
            .name("manager")
            .description("Manager that delegates to the researcher and calculator agents as AgentTools.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a manager manager. You have two specialist agents available as tools:
                - researcher: for looking up information
                - calculator: for math computations

                Use the appropriate manager tool to answer the user's question.
                You can call multiple manager tools if needed.
                """)
            .tools(AgentTool.create(researcher), AgentTool.create(calculator))
            .build();

        AgentResult result = Agentspan.run(manager,
            "Look up information about Python and Rust, then calculate "
            + "what percentage of Python's 4 key use cases overlap with Rust's 4 use cases.");
        result.printResult();

        Agentspan.shutdown();
    }
}
