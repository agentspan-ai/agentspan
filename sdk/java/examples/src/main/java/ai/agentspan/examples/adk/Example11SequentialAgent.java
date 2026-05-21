// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.agents.SequentialAgent;

/**
 * Example Adk 11 — Sequential Agent Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/11_sequential_agent.py</code>.
 *
 * <p>Demonstrates: native ADK {@link SequentialAgent} runs sub-agents in
 * order — researcher → writer → editor. The bridge emits
 * {@code _type: SequentialAgent} so the server compiles this as a Conductor
 * sequential workflow rather than the default handoff strategy.
 */
public class Example11SequentialAgent {

    public static void main(String[] args) {
        // Step 1: Research pipeline gathers facts
        LlmAgent researcher = LlmAgent.builder()
            .name("researcher")
            .description("Gathers 3 key research facts on the user's topic.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research assistant. Given the user's topic, "
                + "provide 3 key facts about it in a numbered list. Be concise.")
            .outputKey("research_findings")
            .build();

        // Step 2: Writer pipeline takes the research and writes a summary
        LlmAgent writer = LlmAgent.builder()
            .name("writer")
            .description("Writes an engaging summary paragraph from the researcher's findings.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a skilled writer. Take the research provided in the conversation "
                + "and write a single engaging paragraph summarizing the key points. "
                + "Keep it under 100 words.")
            .outputKey("draft_summary")
            .build();

        // Step 3: Editor pipeline polishes the summary
        LlmAgent editor = LlmAgent.builder()
            .name("editor")
            .description("Polishes the writer's draft for clarity, grammar, and flow.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an editor. Review the paragraph from the writer and improve it. "
                + "Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph.")
            .outputKey("final_paragraph")
            .build();

        // Pipeline: researcher → writer → editor. Native SequentialAgent.
        SequentialAgent pipeline = SequentialAgent.builder()
            .name("content_pipeline")
            .description("Research → write → edit pipeline.")
            .subAgents(researcher, writer, editor)
            .build();

        AgentResult result = Agentspan.run(pipeline, "The history of the Internet");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
