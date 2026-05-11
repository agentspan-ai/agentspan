// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;

import java.util.List;

/**
 * Example Lc4j 02 — Multiple LangChain4j Tool Classes
 *
 * <p>Demonstrates passing multiple separate {@code @Tool}-annotated objects to
 * {@link LangChain4jAgent#from}. All tool methods from every object are merged
 * into a single agent, so the LLM can call any of them.
 *
 * <p>This mirrors how LangChain4j itself supports multiple tool providers — you
 * keep your tool classes separate by concern and compose them at the agent level.
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767}</li>
 *   <li>langchain4j on the classpath (see examples/build.gradle)</li>
 * </ul>
 */
public class ExampleLc4j02MultiTool {

    // ── Tool class 1: Math operations ─────────────────────────────────────────

    static class MathTools {

        @dev.langchain4j.agent.tool.Tool(name = "math_add", value = "Add two integers")
        public int add(
                @dev.langchain4j.agent.tool.P("a") int a,
                @dev.langchain4j.agent.tool.P("b") int b) {
            return a + b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "math_subtract", value = "Subtract b from a")
        public int subtract(
                @dev.langchain4j.agent.tool.P("a") int a,
                @dev.langchain4j.agent.tool.P("b") int b) {
            return a - b;
        }

        @dev.langchain4j.agent.tool.Tool(name = "math_abs", value = "Return the absolute value of a number")
        public int abs(@dev.langchain4j.agent.tool.P("n") int n) {
            return Math.abs(n);
        }
    }

    // ── Tool class 2: String operations ──────────────────────────────────────

    static class StringTools {

        @dev.langchain4j.agent.tool.Tool(name = "str_upper", value = "Convert a string to upper case")
        public String toUpperCase(@dev.langchain4j.agent.tool.P("text") String text) {
            return text == null ? "" : text.toUpperCase();
        }

        @dev.langchain4j.agent.tool.Tool(name = "str_reverse", value = "Reverse the characters in a string")
        public String reverse(@dev.langchain4j.agent.tool.P("text") String text) {
            if (text == null) return "";
            return new StringBuilder(text).reverse().toString();
        }

        @dev.langchain4j.agent.tool.Tool(name = "str_length", value = "Return the number of characters in a string")
        public int length(@dev.langchain4j.agent.tool.P("text") String text) {
            return text == null ? 0 : text.length();
        }
    }

    public static void main(String[] args) {
        MathTools math = new MathTools();
        StringTools strings = new StringTools();

        // Multiple tool objects are passed as varargs — their tools are merged into one agent.
        // The agent can call math_add, math_subtract, str_upper, str_reverse, etc.
        Agent agent = LangChain4jAgent.from(
            "lc4j_multi_tool_agent",
            Settings.LLM_MODEL,
            "You are a helpful assistant with math and string manipulation tools. "
            + "Use the right tool for each part of the task.",
            math,
            strings
        );

        List<ToolDef> tools = agent.getTools();
        System.out.println("Agent: " + agent.getName());
        System.out.println("Total tools merged from both classes: " + tools.size());
        tools.forEach(t -> System.out.println("  - " + t.getName() + ": " + t.getDescription()));

        AgentResult result = Agentspan.run(agent,
            "What is 42 + 58? Then reverse the string 'Agentspan'.");
        result.printResult();

        Agentspan.shutdown();
    }
}
