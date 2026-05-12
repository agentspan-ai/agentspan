// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.time.LocalDate;

/**
 * Example Lc4j 02 — ReAct Agent with Tools
 *
 * <p>Java port of <code>sdk/python/examples/langchain/02_react_with_tools.py</code>.
 * Agent with practical utility tools driven by a ReAct-style loop.
 *
 * <p>Demonstrates:
 * <ul>
 *   <li>Defining tools with {@link Tool @Tool} on a POJO</li>
 *   <li>Passing tools to {@link LangChain4jAgent#from} for a ReAct-style loop</li>
 *   <li>Calculator, string, and date utilities</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>{@code AGENTSPAN_SERVER_URL=http://localhost:6767/api}</li>
 *   <li>{@code AGENTSPAN_LLM_MODEL=openai/gpt-4o} (or any provider supported by the server)</li>
 *   <li>OpenAI/provider key configured in server credentials</li>
 * </ul>
 */
public class ExampleLc4j02ReactWithTools {

    /** LangChain4j tool POJO — mirrors the three @tool functions in the Python file. */
    static class UtilityTools {

        @Tool(name = "calculate",
              value = "Evaluate a safe mathematical expression and return the result. "
                    + "Supports +, -, *, /, **, sqrt, pi. Example: 'sqrt(144)', '2 ** 10'")
        public String calculate(@P("expression") String expression) {
            try {
                String normalized = expression.replace("pi", String.valueOf(Math.PI)).trim();
                double value = ExpressionParser.eval(normalized);
                // Preserve integer-looking outputs (e.g. sqrt(256) -> 16) similar to Python's str(result).
                if (value == Math.floor(value) && !Double.isInfinite(value)) {
                    return ((long) value) + ".0";
                }
                return Double.toString(value);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        @Tool(name = "count_words", value = "Count the number of words in the provided text.")
        public String countWords(@P("text") String text) {
            if (text == null || text.trim().isEmpty()) {
                return "0 words";
            }
            int n = text.trim().split("\\s+").length;
            return n + " words";
        }

        @Tool(name = "get_today", value = "Return today's date in YYYY-MM-DD format.")
        public String getToday() {
            return LocalDate.now().toString();
        }
    }

    /**
     * Minimal safe expression evaluator supporting +, -, *, /, **, parentheses,
     * sqrt(x), and numeric literals. Used so the example does not require any
     * extra dependencies. Mirrors the small surface used by Python's
     * {@code eval(expression, {"sqrt":..., "pi":...})}.
     */
    static final class ExpressionParser {
        private final String src;
        private int pos;

        private ExpressionParser(String src) { this.src = src; this.pos = 0; }

        static double eval(String src) {
            ExpressionParser p = new ExpressionParser(src);
            double v = p.parseAdd();
            p.skipWs();
            if (p.pos != p.src.length()) {
                throw new IllegalArgumentException("Unexpected token at position " + p.pos);
            }
            return v;
        }

        private void skipWs() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private boolean peek(String s) {
            skipWs();
            return src.startsWith(s, pos);
        }

        private boolean consume(String s) {
            if (peek(s)) { pos += s.length(); return true; }
            return false;
        }

        private double parseAdd() {
            double v = parseMul();
            while (true) {
                if (consume("+")) v += parseMul();
                else if (consume("-")) v -= parseMul();
                else break;
            }
            return v;
        }

        private double parseMul() {
            double v = parsePow();
            while (true) {
                if (peek("**")) break; // power binds tighter and is parsed in parsePow
                if (consume("*")) v *= parsePow();
                else if (consume("/")) v /= parsePow();
                else break;
            }
            return v;
        }

        private double parsePow() {
            double base = parseUnary();
            if (consume("**")) {
                double exp = parsePow(); // right-associative
                return Math.pow(base, exp);
            }
            return base;
        }

        private double parseUnary() {
            skipWs();
            if (consume("+")) return parseUnary();
            if (consume("-")) return -parseUnary();
            return parsePrimary();
        }

        private double parsePrimary() {
            skipWs();
            if (consume("(")) {
                double v = parseAdd();
                if (!consume(")")) throw new IllegalArgumentException("Expected ')'");
                return v;
            }
            if (src.startsWith("sqrt", pos)) {
                pos += 4;
                if (!consume("(")) throw new IllegalArgumentException("Expected '(' after sqrt");
                double inner = parseAdd();
                if (!consume(")")) throw new IllegalArgumentException("Expected ')' after sqrt(");
                return Math.sqrt(inner);
            }
            int start = pos;
            while (pos < src.length() && (Character.isDigit(src.charAt(pos)) || src.charAt(pos) == '.')) {
                pos++;
            }
            if (start == pos) throw new IllegalArgumentException("Expected number at position " + pos);
            return Double.parseDouble(src.substring(start, pos));
        }
    }

    public static void main(String[] args) {
        // Python's create_agent(llm, tools=[...]) sends no system prompt unless
        // the caller provides one — match that by passing null instructions.
        Agent agent = LangChain4jAgent.from(
            "react_tools_agent",
            Settings.LLM_MODEL,
            null,
            new UtilityTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "What is sqrt(256)? Also count words in 'the quick brown fox'. What is today's date?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
