// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 13 — Loop Agent
 *
 * <p>Java port of <code>sdk/python/examples/adk/13_loop_agent.py</code>.
 *
 * <p>Demonstrates: Python's {@code LoopAgent} repeats sub-agents for
 * iterative refinement (up to 3 iterations of write → critique). The Java
 * port uses an {@link LlmAgent} coordinator whose instruction expresses
 * the loop semantics.
 */
public class Example13LoopAgent {

    public static void main(String[] args) {
        // Writer drafts content
        LlmAgent writer = LlmAgent.builder()
            .name("draft_writer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a writer. Write or revise a short haiku (3 lines: 5-7-5 syllables) "
                + "about the given topic. If there is feedback from a previous critique in the conversation, "
                + "incorporate it. Output only the haiku, nothing else.")
            .build();

        // Critic reviews and provides feedback
        LlmAgent critic = LlmAgent.builder()
            .name("critic")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a poetry critic. Review the haiku from the writer. "
                + "Check: (1) Does it follow 5-7-5 syllable structure? "
                + "(2) Is the imagery vivid? (3) Is there a seasonal or nature element? "
                + "Provide 1-2 sentences of constructive feedback for improvement.")
            .build();

        // Each iteration: write → critique. Repeat up to 3 times.
        LlmAgent refinementLoop = LlmAgent.builder()
            .name("refinement_loop")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate an iterative refinement loop. Run the cycle "
                + "[draft_writer → critic] up to 3 times (max_iterations=3), "
                + "feeding the critic's feedback back to the writer each pass. "
                + "Return the final polished haiku.")
            .subAgents(writer, critic)
            .build();

        Agent agent = AdkBridge.toAgentspan(refinementLoop);

        AgentResult result = Agentspan.run(agent, "Write a haiku about autumn leaves");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
