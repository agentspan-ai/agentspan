// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * Example Lc4j 18 — Email Drafter
 *
 * <p>Java port of <code>sdk/python/examples/langchain/18_email_drafter.py</code>.
 *
 * <p>Demonstrates email-composition tools: subject-line generation, tone analysis,
 * and template assembly. Mirrors the Python tool names, descriptions, and rule sets.
 */
public class ExampleLc4j18EmailDrafter {

    public static class EmailTools {

        @dev.langchain4j.agent.tool.Tool(
            name = "generate_subject_lines",
            value = "Generate 3 subject line options for an email based on context."
        )
        public String generateSubjectLines(@dev.langchain4j.agent.tool.P("context") String context) {
            String lower = context == null ? "" : context.toLowerCase(Locale.ROOT);
            if (lower.contains("follow up") || lower.contains("followup")) {
                return "Option 1: Following Up: [Meeting/Topic] — Next Steps\n"
                    + "Option 2: Quick Check-in on [Topic]\n"
                    + "Option 3: Re: [Previous Subject] — Any Updates?";
            }
            if (lower.contains("apolog") || lower.contains("sorry")) {
                return "Option 1: My Sincere Apologies Regarding [Issue]\n"
                    + "Option 2: Addressing the Recent [Issue] — My Apologies\n"
                    + "Option 3: I Owe You an Apology";
            }
            if (lower.contains("introduc")) {
                return "Option 1: Introduction: [Your Name] from [Company]\n"
                    + "Option 2: Nice to Connect — [Your Name]\n"
                    + "Option 3: Reaching Out: [Mutual Connection] Suggested We Chat";
            }
            return "Option 1: [Action Required] [Topic]\n"
                + "Option 2: Update on [Topic]\n"
                + "Option 3: Quick Question About [Topic]";
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "check_email_tone",
            value = "Analyze the tone of an email draft and flag potential issues."
        )
        public String checkEmailTone(@dev.langchain4j.agent.tool.P("text") String text) {
            List<String> aggressiveWords = Arrays.asList(
                "demand", "must", "immediately", "failure", "unacceptable", "ridiculous"
            );
            List<String> passiveAggressive = Arrays.asList(
                "as I mentioned", "as previously stated", "clearly", "obviously", "simply"
            );

            String t = text == null ? "" : text;
            String lower = t.toLowerCase(Locale.ROOT);
            List<String> issues = new ArrayList<>();
            for (String w : aggressiveWords) {
                if (lower.contains(w)) issues.add("Potentially aggressive tone: '" + w + "'");
            }
            for (String p : passiveAggressive) {
                if (lower.contains(p.toLowerCase(Locale.ROOT))) {
                    issues.add("Potentially passive-aggressive: '" + p + "'");
                }
            }
            int bangs = 0;
            for (int i = 0; i < t.length(); i++) if (t.charAt(i) == '!') bangs++;
            if (bangs > 2) {
                issues.add("Excessive exclamation marks: " + bangs + " found");
            }

            if (issues.isEmpty()) {
                return "Tone analysis: Professional and appropriate. No issues detected.";
            }
            StringBuilder sb = new StringBuilder("Tone issues found:");
            for (String i : issues) sb.append("\n  • ").append(i);
            return sb.toString();
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "format_email_template",
            value = "Assemble a properly formatted email from components."
        )
        public String formatEmailTemplate(
                @dev.langchain4j.agent.tool.P("greeting") String greeting,
                @dev.langchain4j.agent.tool.P("body") String body,
                @dev.langchain4j.agent.tool.P("closing") String closing,
                @dev.langchain4j.agent.tool.P("sender_name") String senderName) {
            return greeting + "\n\n" + body + "\n\n" + closing + "\n" + senderName;
        }
    }

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "email_drafter_agent",
            Settings.LLM_MODEL,
            "You are a professional email writing assistant. Help users draft clear, "
                + "appropriate, and effective emails. Always check tone and suggest subject lines.",
            new EmailTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Draft a professional follow-up email to a client named Sarah after a product demo yesterday. "
                + "Include subject line options and check the tone."
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
