// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Example Adk 08 — Instruction Templating
 *
 * <p>Java port of <code>sdk/python/examples/adk/08_instruction_templating.py</code>.
 *
 * <p>Demonstrates: ADK's instruction templating with {@code {variable}} syntax.
 * Variables are resolved from session state at runtime by the server.
 */
public class Example08InstructionTemplating {

    static class PrefTools {

        @Tool(name = "get_user_preferences", value = "Look up user preferences.")
        public Map<String, Object> getUserPreferences(@P("user_id") String userId) {
            Map<String, Map<String, Object>> users = new LinkedHashMap<>();
            users.put("user_001", Map.of(
                "name", "Alice",
                "language", "English",
                "expertise", "beginner",
                "preferred_format", "bullet points"));
            users.put("user_002", Map.of(
                "name", "Bob",
                "language", "English",
                "expertise", "advanced",
                "preferred_format", "detailed paragraphs"));
            return users.getOrDefault(userId,
                Map.of("name", "Guest", "expertise", "intermediate", "preferred_format", "concise"));
        }

        @Tool(name = "search_tutorials", value = "Search for tutorials matching a topic and skill level.")
        public Map<String, Object> searchTutorials(
                @P("topic") String topic,
                @P("level") String level) {
            String lvl = level == null ? "intermediate" : level.toLowerCase();
            String key = topic.toLowerCase() + "::" + lvl;
            Map<String, List<String>> tutorials = new LinkedHashMap<>();
            tutorials.put("python::beginner", List.of(
                "Python Basics: Variables and Types",
                "Your First Python Function",
                "Lists and Loops for Beginners"));
            tutorials.put("python::advanced", List.of(
                "Metaclasses and Descriptors",
                "Async IO Deep Dive",
                "CPython Internals"));
            List<String> results = tutorials.getOrDefault(key, List.of("General " + topic + " tutorial"));
            return Map.of("topic", topic, "level", lvl, "tutorials", results);
        }
    }

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("adaptive_tutor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a personalized programming tutor. "
                + "The current user is {user_name} with {expertise_level} expertise. "
                + "Adapt your explanations to their level. "
                + "Use the search_tutorials tool to find appropriate learning resources.")
            .tools(new PrefTools())
            .build();

        AgentResult result = Agentspan.run(agent,
            "I want to learn Python. What tutorials do you recommend?");
        result.printResult();

        Agentspan.shutdown();
    }
}
