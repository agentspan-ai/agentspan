// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.langchain;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.openai.OpenAiChatModel;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example Lc4j 11 — Code Review Agent (native LangChain4j SDK)
 *
 * <p>Java port of <code>sdk/python/examples/langchain/11_code_review_agent.py</code>.
 *
 * <p>Demonstrates: static-analysis tools (syntax, complexity, naming) bundled
 * into a single LangChain4j agent. The Python original parses Python code with
 * the {@code ast} module; this Java port uses regex/line-based heuristics that
 * mirror the same rules (branch counting, PEP-8 snake_case, syntax sanity).
 */
public class Example11CodeReviewAgent {

    static class CodeReviewTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "check_syntax",
            value = "Check Python code for syntax errors. "
                  + "Args: code: Python source code to validate."
        )
        public String checkSyntax(@dev.langchain4j.agent.tool.P("code") String code) {
            // Lightweight heuristics: balanced parens/brackets and balanced colon/indent
            int paren = 0, bracket = 0, brace = 0;
            int line = 1;
            for (int i = 0; i < code.length(); i++) {
                char c = code.charAt(i);
                if (c == '\n') line++;
                else if (c == '(') paren++;
                else if (c == ')') { paren--; if (paren < 0) return "Syntax error at line " + line + ": unbalanced ')'."; }
                else if (c == '[') bracket++;
                else if (c == ']') { bracket--; if (bracket < 0) return "Syntax error at line " + line + ": unbalanced ']'."; }
                else if (c == '{') brace++;
                else if (c == '}') { brace--; if (brace < 0) return "Syntax error at line " + line + ": unbalanced '}'."; }
            }
            if (paren != 0) return "Syntax error: unbalanced parentheses.";
            if (bracket != 0) return "Syntax error: unbalanced brackets.";
            if (brace != 0) return "Syntax error: unbalanced braces.";
            return "Syntax OK — no syntax errors found.";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "measure_complexity",
            value = "Estimate cyclomatic complexity by counting branches in Python code. "
                  + "Args: code: Python source code to analyze."
        )
        public String measureComplexity(@dev.langchain4j.agent.tool.P("code") String code) {
            // Count occurrences of branching keywords at word boundaries:
            //   if, for, while, except, with, assert
            String[] kws = {"if", "elif", "for", "while", "except", "with", "assert"};
            int branches = 0;
            for (String kw : kws) {
                Pattern p = Pattern.compile("(?m)^\\s*" + Pattern.quote(kw) + "\\b");
                Matcher m = p.matcher(code);
                while (m.find()) branches++;
            }
            int score = branches + 1;
            String rating = score <= 5 ? "Low" : (score <= 10 ? "Medium" : "High");
            return "Cyclomatic complexity: " + score + " (" + rating + "). Branch count: " + branches + ".";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "check_naming_conventions",
            value = "Check whether function and variable names follow PEP 8 snake_case convention. "
                  + "Args: code: Python source code to check."
        )
        public String checkNamingConventions(@dev.langchain4j.agent.tool.P("code") String code) {
            List<String> violations = new ArrayList<>();

            // Function definitions: def Name(... — flag if not lower-case
            Pattern defPat = Pattern.compile("\\bdef\\s+([A-Za-z_][A-Za-z0-9_]*)");
            Matcher defM = defPat.matcher(code);
            while (defM.find()) {
                String fn = defM.group(1);
                if (!fn.equals(fn.toLowerCase())) {
                    violations.add("Function '" + fn + "' should be snake_case.");
                }
            }

            // Parameters in function defs — flag if not lower-case / not ALL_CAPS
            Pattern argsPat = Pattern.compile("\\bdef\\s+[A-Za-z_][A-Za-z0-9_]*\\s*\\(([^)]*)\\)");
            Matcher argsM = argsPat.matcher(code);
            while (argsM.find()) {
                String argList = argsM.group(1);
                for (String part : argList.split(",")) {
                    String name = part.trim().split("[:=]")[0].trim();
                    if (name.isEmpty() || name.equals("self") || name.equals("cls")) continue;
                    if (!isValidIdent(name)) continue;
                    if (!name.equals(name.toLowerCase()) && !name.equals(name.toUpperCase())) {
                        violations.add("Variable '" + name + "' should be snake_case (or ALL_CAPS for constants).");
                    }
                }
            }

            // Simple assignment targets: ^name = ... — flag if not lower-case / not ALL_CAPS
            Pattern asgnPat = Pattern.compile("(?m)^\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*=(?!=)");
            Matcher asgnM = asgnPat.matcher(code);
            while (asgnM.find()) {
                String nm = asgnM.group(1);
                if (!nm.equals(nm.toLowerCase()) && !nm.equals(nm.toUpperCase())) {
                    violations.add("Variable '" + nm + "' should be snake_case (or ALL_CAPS for constants).");
                }
            }

            if (violations.isEmpty()) {
                return "Naming conventions OK — all names follow PEP 8.";
            }
            StringBuilder sb = new StringBuilder("Naming issues:");
            int limit = Math.min(5, violations.size());
            for (int i = 0; i < limit; i++) {
                sb.append("\n  • ").append(violations.get(i));
            }
            return sb.toString();
        }

        private static boolean isValidIdent(String s) {
            if (s.isEmpty()) return false;
            char c = s.charAt(0);
            if (!(Character.isLetter(c) || c == '_')) return false;
            for (int i = 1; i < s.length(); i++) {
                char ch = s.charAt(i);
                if (!(Character.isLetterOrDigit(ch) || ch == '_')) return false;
            }
            return true;
        }
    }

    private static final String SAMPLE_CODE = "\n"
            + "def ProcessUserData(UserName, UserAge):\n"
            + "    if UserAge < 0:\n"
            + "        return None\n"
            + "    if UserAge < 18:\n"
            + "        if UserAge < 13:\n"
            + "            return 'child'\n"
            + "        else:\n"
            + "            return 'teen'\n"
            + "    return 'adult'\n";

    public static void main(String[] args) {
        // apiKey is required by LangChain4j's builder but unused — Agentspan
        // runs the LLM call on the server with server-registered credentials.
        ChatModel model = OpenAiChatModel.builder()
            .apiKey("agentspan-server-handles-credentials")
            .modelName("gpt-4o-mini")
            .build();

        // Drop-in overload — fold the system prompt into the user message.
        AgentResult result = Agentspan.run(
            model,
            "You are an expert code reviewer. Analyze code thoroughly using the available tools. "
            + "Report findings clearly and suggest improvements.\n\n"
            + "Review this Python code and identify all issues:\n```python" + SAMPLE_CODE + "```",
            new CodeReviewTools()
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
