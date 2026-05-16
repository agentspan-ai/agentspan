// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Lc4j 09 — Math Calculator
 *
 * <p>Java port of <code>sdk/python/examples/langchain/09_math_calculator.py</code>.
 *
 * <p>Demonstrates: safe arithmetic expression evaluation, unit conversion, and
 * descriptive statistics tools combined in a single LangChain4j agent.
 */
public class ExampleLc4j09MathCalculator {

    /**
     * Recursive-descent evaluator for arithmetic expressions over doubles.
     *
     * <p>Mirrors Python's {@code _safe_eval} which uses {@code ast.parse}.
     * Supports + - * / ** % // and unary -. Operator precedence:
     * <ol>
     *   <li>unary -</li>
     *   <li>** (right-associative)</li>
     *   <li>* / % //</li>
     *   <li>+ -</li>
     * </ol>
     */
    static class SafeEval {
        private final String src;
        private int pos;

        SafeEval(String src) {
            this.src = src;
            this.pos = 0;
        }

        static double eval(String expression) {
            SafeEval e = new SafeEval(expression);
            double v = e.parseExpr();
            e.skipWs();
            if (e.pos != e.src.length()) {
                throw new IllegalArgumentException("Unexpected trailing input at position " + e.pos);
            }
            return v;
        }

        private void skipWs() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        // expr := term (('+'|'-') term)*
        private double parseExpr() {
            double v = parseTerm();
            while (true) {
                skipWs();
                if (pos < src.length() && src.charAt(pos) == '+') { pos++; v = v + parseTerm(); }
                else if (pos < src.length() && src.charAt(pos) == '-') { pos++; v = v - parseTerm(); }
                else break;
            }
            return v;
        }

        // term := factor (('*'|'/'|'%'|'//') factor)*
        private double parseTerm() {
            double v = parseFactor();
            while (true) {
                skipWs();
                if (pos < src.length() && src.charAt(pos) == '*' && !(pos + 1 < src.length() && src.charAt(pos + 1) == '*')) {
                    pos++; v = v * parseFactor();
                } else if (pos + 1 < src.length() && src.charAt(pos) == '/' && src.charAt(pos + 1) == '/') {
                    pos += 2; v = Math.floor(v / parseFactor());
                } else if (pos < src.length() && src.charAt(pos) == '/') {
                    pos++; v = v / parseFactor();
                } else if (pos < src.length() && src.charAt(pos) == '%') {
                    pos++; v = v % parseFactor();
                } else break;
            }
            return v;
        }

        // factor := ('-' factor) | power
        private double parseFactor() {
            skipWs();
            if (pos < src.length() && src.charAt(pos) == '-') {
                pos++;
                return -parseFactor();
            }
            if (pos < src.length() && src.charAt(pos) == '+') {
                pos++;
                return parseFactor();
            }
            return parsePower();
        }

        // power := atom ('**' factor)?    (right-associative)
        private double parsePower() {
            double base = parseAtom();
            skipWs();
            if (pos + 1 < src.length() && src.charAt(pos) == '*' && src.charAt(pos + 1) == '*') {
                pos += 2;
                double exp = parseFactor();
                return Math.pow(base, exp);
            }
            return base;
        }

        // atom := number | '(' expr ')'
        private double parseAtom() {
            skipWs();
            if (pos < src.length() && src.charAt(pos) == '(') {
                pos++;
                double v = parseExpr();
                skipWs();
                if (pos >= src.length() || src.charAt(pos) != ')') {
                    throw new IllegalArgumentException("Missing closing paren at position " + pos);
                }
                pos++;
                return v;
            }
            return parseNumber();
        }

        private double parseNumber() {
            skipWs();
            int start = pos;
            while (pos < src.length()
                    && (Character.isDigit(src.charAt(pos)) || src.charAt(pos) == '.'
                            || src.charAt(pos) == 'e' || src.charAt(pos) == 'E'
                            || ((src.charAt(pos) == '+' || src.charAt(pos) == '-')
                                && pos > start
                                && (src.charAt(pos - 1) == 'e' || src.charAt(pos - 1) == 'E')))) {
                pos++;
            }
            if (start == pos) {
                throw new IllegalArgumentException("Expected number at position " + pos);
            }
            return Double.parseDouble(src.substring(start, pos));
        }
    }

    static class MathTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "evaluate",
            value = "Evaluate an arithmetic expression (+, -, *, /, **, %, //). "
                  + "Args: expression: A math expression like '(3 + 5) * 2 ** 4'."
        )
        public String evaluate(@dev.langchain4j.agent.tool.P("expression") String expression) {
            try {
                double v = SafeEval.eval(expression);
                // Mirror Python str(float/int) — drop ".0" when integer-valued
                if (v == Math.floor(v) && !Double.isInfinite(v)) {
                    return Long.toString((long) v);
                }
                return Double.toString(v);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "convert_length",
            value = "Convert between length units: meters, kilometers, miles, feet, inches, cm. "
                  + "Args: value: The numeric value to convert. "
                  + "from_unit: Source unit (m, km, mi, ft, in, cm). "
                  + "to_unit: Target unit (m, km, mi, ft, in, cm)."
        )
        public String convertLength(
                @dev.langchain4j.agent.tool.P("value") double value,
                @dev.langchain4j.agent.tool.P("from_unit") String fromUnit,
                @dev.langchain4j.agent.tool.P("to_unit") String toUnit) {
            java.util.Map<String, Double> toMeters = new java.util.LinkedHashMap<>();
            toMeters.put("m", 1.0);
            toMeters.put("km", 1000.0);
            toMeters.put("mi", 1609.344);
            toMeters.put("ft", 0.3048);
            toMeters.put("in", 0.0254);
            toMeters.put("cm", 0.01);

            String fu = stripTrailingS(fromUnit.toLowerCase());
            String tu = stripTrailingS(toUnit.toLowerCase());
            if (!toMeters.containsKey(fu) || !toMeters.containsKey(tu)) {
                return "Unknown unit(s): " + fromUnit + ", " + toUnit;
            }
            double result = value * toMeters.get(fu) / toMeters.get(tu);
            return String.format("%s %s = %.4f %s", trimNum(value), fromUnit, result, toUnit);
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "statistics",
            value = "Compute mean, median, min, max, and sum for a comma-separated list of numbers. "
                  + "Args: numbers: Comma-separated numbers, e.g. '3, 7, 2, 9, 4'."
        )
        public String statistics(@dev.langchain4j.agent.tool.P("numbers") String numbers) {
            try {
                String[] parts = numbers.split(",");
                double[] nums = new double[parts.length];
                for (int i = 0; i < parts.length; i++) {
                    nums[i] = Double.parseDouble(parts[i].trim());
                }
                double[] sorted = nums.clone();
                java.util.Arrays.sort(sorted);
                int n = nums.length;
                double median = (n % 2 != 0) ? sorted[n / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0;
                double sum = 0;
                double min = nums[0];
                double max = nums[0];
                for (double x : nums) { sum += x; if (x < min) min = x; if (x > max) max = x; }
                double mean = sum / n;
                return String.format(
                    "Count: %d, Sum: %.2f, Mean: %.2f, Median: %.2f, Min: %.2f, Max: %.2f",
                    n, sum, mean, median, min, max);
            } catch (Exception e) {
                return "Error: " + e.getMessage();
            }
        }

        private static String stripTrailingS(String s) {
            return s.endsWith("s") ? s.substring(0, s.length() - 1) : s;
        }

        private static String trimNum(double v) {
            if (v == Math.floor(v) && !Double.isInfinite(v)) {
                return Long.toString((long) v);
            }
            return Double.toString(v);
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "math_calculator_agent",
            Settings.LLM_MODEL,
            "You are a precise math assistant. Always use tools to compute exact answers.",
            new MathTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "What is (2 ** 8) + (15 * 7)? Convert 5 miles to kilometers. "
            + "What is the mean and median of 12, 7, 3, 19, 5, 8?"
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
