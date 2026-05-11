// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Lc4j 01 — Basic LangChain4j Tool Integration
 *
 * <p>Shows how to bring existing LangChain4j {@code @Tool}-annotated POJOs into
 * Agentspan without rewriting them. {@link LangChain4jAgent#from} wraps every
 * {@code @Tool} method as an Agentspan worker tool — you keep your existing
 * LangChain4j tool classes unchanged.
 *
 * <p>Key points:
 * <ul>
 *   <li>{@code LangChain4jAgent.from()} accepts any number of tool objects</li>
 *   <li>{@link LangChain4jAgent#isLangChain4jTools} detects whether a POJO has {@code @Tool} methods</li>
 *   <li>The returned {@link Agent} works with the full Agentspan runtime (plan, run, deploy)</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767}</li>
 *   <li>langchain4j on the classpath (see examples/build.gradle)</li>
 * </ul>
 */
public class ExampleLc4j01BasicAgent {

    // ── LangChain4j tool class (unchanged from your existing codebase) ────────

    static class CalculatorTools {

        @dev.langchain4j.agent.tool.Tool(name = "add", value = "Add two numbers and return the sum")
        public double add(
                @dev.langchain4j.agent.tool.P("a") double a,
                @dev.langchain4j.agent.tool.P("b") double b) {
            return a + b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "multiply", value = "Multiply two numbers and return the product")
        public double multiply(
                @dev.langchain4j.agent.tool.P("a") double a,
                @dev.langchain4j.agent.tool.P("b") double b) {
            return a * b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "square_root", value = "Return the square root of a number")
        public double squareRoot(@dev.langchain4j.agent.tool.P("n") double n) {
            return Math.sqrt(n);
        }
    }

    public static void main(String[] args) {
        CalculatorTools calculator = new CalculatorTools();

        // Detect whether the POJO carries @Tool methods (useful when tools come from unknown sources)
        System.out.println("Is LangChain4j tool provider: "
            + LangChain4jAgent.isLangChain4jTools(calculator));

        // Bring existing LangChain4j tools into Agentspan — no rewriting needed.
        // LangChain4jAgent.from() reflects over @Tool annotations and registers
        // each method as an Agentspan worker tool.
        Agent agent = LangChain4jAgent.from(
            "lc4j_calculator",
            Settings.LLM_MODEL,
            "You are a calculator assistant. Use your tools to answer math questions accurately.",
            calculator
        );

        System.out.println("Agent: " + agent.getName());
        System.out.println("Tools: " + agent.getTools().size());

        AgentResult result = Agentspan.run(agent, "What is the square root of 144, then add 5 to it?");
        result.printResult();

        Agentspan.shutdown();
    }
}
