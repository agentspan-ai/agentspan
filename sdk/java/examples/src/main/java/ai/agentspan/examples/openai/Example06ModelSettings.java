// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.openai;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.OpenAIAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example OpenAi 06 — Model Settings
 *
 * <p>Java port of <code>sdk/python/examples/openai/06_model_settings.py</code>.
 *
 * <p>Demonstrates: two agents with identical wiring but different stylistic
 * intent — a high-temperature creative writer and a low-temperature precise
 * code reviewer.
 *
 * <p>Python parity gap: the current {@link OpenAIAgent} builder does not
 * expose {@code model_settings} (temperature, max_tokens). The intended
 * settings from the Python original are documented here so a future
 * OpenAIAgent builder extension can surface them:
 * <ul>
 *   <li>{@code creative_writer}: {@code temperature=0.9, max_tokens=500}.</li>
 *   <li>{@code code_reviewer}: {@code temperature=0.1, max_tokens=300}.</li>
 * </ul>
 *
 * <p>Requirements:
 * <ul>
 *   <li>AGENTSPAN_SERVER_URL=http://localhost:6767/api</li>
 *   <li>AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini</li>
 * </ul>
 */
public class Example06ModelSettings {

    public static void main(String[] args) {
        // Creative agent — high-temperature intent (0.9) per Python original.
        Agent creativeAgent = OpenAIAgent.builder()
                .name("creative_writer")
                .instructions(
                        "You are a creative writing assistant. Write with vivid imagery "
                                + "and unexpected metaphors. Be bold and imaginative.")
                .model(Settings.LLM_MODEL)
                .build();

        // Precise agent — low-temperature intent (0.1) per Python original.
        Agent preciseAgent = OpenAIAgent.builder()
                .name("code_reviewer")
                .instructions(
                        "You are a precise code reviewer. Analyze code snippets for bugs, "
                                + "security issues, and best practices. Be concise and specific.")
                .model(Settings.LLM_MODEL)
                .build();

        System.out.println("=== Creative Agent (temp=0.9) ===");
        AgentResult creative = Agentspan.run(
                creativeAgent,
                "Write a two-sentence story about a robot learning to paint.");
        creative.printResult();

        System.out.println("\n=== Precise Agent (temp=0.1) ===");
        AgentResult precise = Agentspan.run(
                preciseAgent,
                "Review this Python code: `data = eval(user_input)`");
        precise.printResult();

        Agentspan.shutdown();
    }
}
