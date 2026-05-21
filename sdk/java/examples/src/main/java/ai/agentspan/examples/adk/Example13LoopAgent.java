// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.agents.LoopAgent;

/**
 * Example Adk 13 — Loop Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/13_loop_agent.py</code>.
 *
 * <p>Demonstrates: native ADK {@link LoopAgent} repeats sub-agents for
 * iterative refinement (up to 3 iterations of write → critique). The
 * {@code maxIterations} setting is propagated via the bridge so the server
 * compiles a Conductor DO_WHILE with the correct upper bound.
 */
public class Example13LoopAgent {

    public static void main(String[] args) {
        // Writer drafts content
        LlmAgent writer = LlmAgent.builder()
            .name("draft_writer")
            .description("Writes or revises a 5-7-5 haiku, incorporating any prior critique feedback.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a writer. Write or revise a short haiku (3 lines: 5-7-5 syllables)
                about the given topic. If there is feedback from a previous critique in the conversation,
                incorporate it. Output only the haiku, nothing else.
                """)
            .build();

        // Critic reviews and provides feedback
        LlmAgent critic = LlmAgent.builder()
            .name("critic")
            .description("Reviews the writer's haiku for structure, imagery, and seasonal feel.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a poetry critic. Review the haiku from the writer.
                Check: (1) Does it follow 5-7-5 syllable structure?
                (2) Is the imagery vivid? (3) Is there a seasonal or nature element?
                Provide 1-2 sentences of constructive feedback for improvement.
                """)
            .build();

        // Each iteration: write → critique. Native LoopAgent with maxIterations=3.
        LoopAgent refinementLoop = LoopAgent.builder()
            .name("refinement_loop")
            .description("Iteratively refine a haiku until the critic is satisfied.")
            .maxIterations(3)
            .subAgents(writer, critic)
            .build();

        AgentResult result = Agentspan.run(refinementLoop, "Write a haiku about autumn leaves");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
