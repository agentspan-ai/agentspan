// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.LangChain4jAgent;
import ai.agentspan.model.AgentResult;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example Lc4j 16 — Content Writer
 *
 * <p>Java port of <code>sdk/python/examples/langchain/16_content_writer.py</code>.
 *
 * <p>Demonstrates: SEO-oriented content analysis tools — Flesch-Kincaid grade
 * level, keyword density, and title-template suggestions.
 */
public class ExampleLc4j16ContentWriter {

    static class ContentWriterTools {

        private static final Pattern SENTENCE_SPLIT = Pattern.compile("[.!?]+");
        private static final Pattern VOWELS = Pattern.compile("[aeiouAEIOU]");

        @dev.langchain4j.agent.tool.Tool(
            name = "analyze_readability",
            value = "Estimate readability using Flesch-Kincaid grade level approximation. "
                  + "Args: text: The text to analyze."
        )
        public String analyzeReadability(@dev.langchain4j.agent.tool.P("text") String text) {
            int sentences = Math.max(1, SENTENCE_SPLIT.split(text).length);
            String[] words = text.trim().isEmpty() ? new String[0] : text.trim().split("\\s+");
            int wordCount = Math.max(1, words.length);

            int syllables = 0;
            for (String w : words) {
                Matcher m = VOWELS.matcher(w);
                int c = 0;
                while (m.find()) c++;
                syllables += Math.max(1, c);
            }

            double fkGrade = 0.39 * ((double) wordCount / sentences)
                           + 11.8 * ((double) syllables / wordCount)
                           - 15.59;
            fkGrade = Math.max(1, Math.min(20, fkGrade));

            String level;
            if (fkGrade <= 6) level = "Elementary";
            else if (fkGrade <= 10) level = "Middle School";
            else if (fkGrade <= 14) level = "High School / College";
            else level = "Expert / Academic";

            return String.format(
                "Readability: Grade %.1f (%s). Words: %d, Sentences: %d, Avg words/sentence: %.1f.",
                fkGrade, level, wordCount, sentences, (double) wordCount / sentences);
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "check_keyword_density",
            value = "Check how often a keyword appears in the text (density as % of total words). "
                  + "Args: text: The content to analyze. "
                  + "keyword: The target keyword or phrase."
        )
        public String checkKeywordDensity(
                @dev.langchain4j.agent.tool.P("text") String text,
                @dev.langchain4j.agent.tool.P("keyword") String keyword) {
            String[] words = text.toLowerCase().trim().isEmpty()
                ? new String[0]
                : text.toLowerCase().trim().split("\\s+");
            int total = words.length;
            if (total == 0) return "Empty text.";
            String kw = keyword == null ? "" : keyword.toLowerCase();
            int count = 0;
            for (String w : words) {
                if (w.contains(kw)) count++;
            }
            double density = ((double) count / total) * 100.0;
            String rec;
            if (density < 1) rec = "Too sparse";
            else if (density > 3) rec = "Keyword stuffing risk";
            else rec = "OK";
            return String.format("Keyword '%s': %d occurrence(s) in %d words (%.1f%%). Status: %s.",
                keyword, count, total, density, rec);
        }

        @dev.langchain4j.agent.tool.Tool(
            name = "suggest_title_variations",
            value = "Generate title format suggestions for a content topic. "
                  + "Args: topic: The main topic of the content."
        )
        public String suggestTitleVariations(@dev.langchain4j.agent.tool.P("topic") String topic) {
            String t = topic == null ? "" : titleCase(topic);
            String[] templates = new String[] {
                "The Complete Guide to " + t,
                "How to Master " + t + " in 2025",
                t + ": Everything You Need to Know",
                "Top 10 " + t + " Tips for Beginners",
                "Why " + t + " Matters More Than Ever"
            };
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < templates.length; i++) {
                if (i > 0) sb.append("\n");
                sb.append("• ").append(templates[i]);
            }
            return sb.toString();
        }

        /** Mirrors Python {@code str.title()}: capitalize the first letter of each word. */
        private static String titleCase(String s) {
            StringBuilder out = new StringBuilder();
            boolean newWord = true;
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                if (Character.isLetter(c)) {
                    out.append(newWord ? Character.toUpperCase(c) : Character.toLowerCase(c));
                    newWord = false;
                } else {
                    out.append(c);
                    newWord = true;
                }
            }
            return out.toString();
        }
    }

    private static final String SAMPLE_CONTENT = "\n"
            + "Python programming is a versatile programming language used in many domains.\n"
            + "Python programming makes it easy to write clean code. Many developers choose\n"
            + "Python programming for data science tasks. Python programming also works well\n"
            + "for web development. If you want to learn Python programming, start with the basics.\n";

    public static void main(String[] args) {
        Agent agent = LangChain4jAgent.from(
            "content_writer_agent",
            Settings.LLM_MODEL,
            "You are a professional content strategist and writer. "
            + "Help users create clear, engaging, SEO-friendly content. "
            + "Use tools to analyze and improve content quality.",
            new ContentWriterTools()
        );

        AgentResult result = Agentspan.run(
            agent,
            "Analyze this content for readability and keyword density for 'python programming'. "
            + "Also suggest better title options for an article about Python.\n\n" + SAMPLE_CONTENT
        );
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
