// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langgraph;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

/**
 * Example LangGraph 09 — Specialized math agent with multiple arithmetic tools.
 *
 * <p>Mirrors <code>sdk/python/examples/langgraph/09_math_agent.py</code>. The
 * LangGraph4j {@code AgentExecutor} runs the ReAct loop and chains tool calls
 * across multi-step problems.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>A single agent with many related tools (a math domain)</li>
 *   <li>Chained tool calls solving multi-step expressions</li>
 *   <li>Error reporting via tool return values (no exceptions to LLM)</li>
 * </ul>
 */
public class Example09MathAgent {

    static class MathTools {

        @Tool("Add two numbers and return the sum.")
        public String add(@P("a") double a, @P("b") double b) {
            return String.valueOf(a + b);
        }

        @Tool("Subtract b from a and return the result.")
        public String subtract(@P("a") double a, @P("b") double b) {
            return String.valueOf(a - b);
        }

        @Tool("Multiply two numbers and return the product.")
        public String multiply(@P("a") double a, @P("b") double b) {
            return String.valueOf(a * b);
        }

        @Tool("Divide a by b. Returns an error if b is zero.")
        public String divide(@P("a") double a, @P("b") double b) {
            if (b == 0.0) return "Error: Division by zero is undefined.";
            return String.valueOf(a / b);
        }

        @Tool("Raise base to the given exponent and return the result.")
        public String power(@P("base") double base, @P("exponent") double exponent) {
            return String.valueOf(Math.pow(base, exponent));
        }

        @Tool("Compute the square root of n. Returns an error for negative numbers.")
        public String sqrt(@P("n") double n) {
            if (n < 0) return "Error: Cannot compute the square root of a negative number (" + n + ").";
            return String.valueOf(Math.sqrt(n));
        }

        @Tool("Compute the factorial of a non-negative integer n (n <= 20).")
        public String factorial(@P("n") int n) {
            if (n < 0) return "Error: Factorial is not defined for negative numbers.";
            if (n > 20) return "Error: Input too large (max 20 to avoid overflow).";
            long f = 1;
            for (int i = 2; i <= n; i++) f *= i;
            return String.valueOf(f);
        }
    }

    public static void main(String[] args) {
        ChatModel model = OpenAiChatModel.builder()
                .apiKey(System.getenv().getOrDefault("OPENAI_API_KEY", "unused"))
                .modelName("gpt-4o-mini")
                .build();

        Agent agent = LangGraphBridge.toAgentspan(
                "math_agent",
                model,
                "You are a math agent. Use the provided tools to compute every "
                + "arithmetic step rather than doing it in your head. Show the result.",
                new MathTools()
        );

        AgentResult result = Agentspan.run(
                agent,
                "Calculate: (2^10 + sqrt(144)) / 4, then compute 5! and tell me both answers."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
