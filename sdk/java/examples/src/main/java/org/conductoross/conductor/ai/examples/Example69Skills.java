// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.tools.AgentTool;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.skill.Skill;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

/**
 * Example 69 — Skills
 *
 * <p>Loads an agentskills.io skill directory as an Agentspan Agent. Skill scripts
 * become worker tools, and resource files are available through the generated
 * read_skill_file tool.
 *
 * <p>Usage:
 * <pre>
 *   AGENTSPAN_SERVER_URL=http://localhost:6767/api \
 *   AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini \
 *   ./gradlew :examples:run -PmainClass=org.conductoross.conductor.ai.examples.Example69Skills \
 *     --args="/path/to/skill 'Review this repository'"
 * </pre>
 */
public class Example69Skills {

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        Path skillPath = args.length > 0
            ? Paths.get(args[0])
            : Paths.get(System.getProperty("user.home"), ".claude", "skills", "dg");
        String prompt = args.length > 1
            ? args[1]
            : "Run this skill against the current request and return a concise result.";

        if (!Files.exists(skillPath.resolve("SKILL.md"))) {
            throw new IllegalArgumentException(
                "Expected a skill directory containing SKILL.md: " + skillPath.toAbsolutePath());
        }

        Agent skillAgent = Skill.skill(
            skillPath,
            Settings.LLM_MODEL,
            null,
            null,
            List.of(Paths.get(System.getProperty("user.home"), ".agents", "skills")));

        AgentResult direct = runtime.run(skillAgent, prompt);
        direct.printResult();

        Agent parent = Agent.builder()
            .name("skill_tool_manager_69")
            .model(Settings.LLM_MODEL)
            .instructions(
                "Use the wrapped skill tool for the user request, then return the skill result.")
            .tools(List.of(AgentTool.from(skillAgent, "Run the loaded skill")))
            .maxTurns(4)
            .build();

        AgentResult viaTool = runtime.run(parent, prompt);
        viaTool.printResult();

        runtime.shutdown();
    }
}
