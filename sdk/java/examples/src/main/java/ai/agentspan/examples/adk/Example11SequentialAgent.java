// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 11 — Sequential Agent Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/11_sequential_agent.py</code>.
 *
 * <p>Demonstrates: a sequential pipeline coordinator (researcher → writer →
 * editor). Native ADK has a {@code SequentialAgent}, but the Agentspan
 * {@link AdkBridge} extracts {@link LlmAgent}s and their sub-agents, so the
 * pipeline is modeled as a coordinator {@code LlmAgent} whose instruction
 * dictates ordered execution.
 */
public class Example11SequentialAgent {

    public static void main(String[] args) {
        // Step 1: Research agent gathers facts
        LlmAgent researcher = LlmAgent.builder()
            .name("researcher")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research assistant. Given the user's topic, "
                + "provide 3 key facts about it in a numbered list. Be concise.")
            .build();

        // Step 2: Writer agent takes the research and writes a summary
        LlmAgent writer = LlmAgent.builder()
            .name("writer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a skilled writer. Take the research provided in the conversation "
                + "and write a single engaging paragraph summarizing the key points. "
                + "Keep it under 100 words.")
            .build();

        // Step 3: Editor agent polishes the summary
        LlmAgent editor = LlmAgent.builder()
            .name("editor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an editor. Review the paragraph from the writer and improve it. "
                + "Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph.")
            .build();

        // Pipeline: researcher → writer → editor
        LlmAgent pipeline = LlmAgent.builder()
            .name("content_pipeline")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate a content pipeline. Execute the steps in this order:\n"
                + "1. researcher gathers 3 key facts\n"
                + "2. writer composes a paragraph from those facts\n"
                + "3. editor polishes the paragraph\n"
                + "Return the editor's final paragraph.")
            .subAgents(researcher, writer, editor)
            .build();

        Agent agent = AdkBridge.toAgentspan(pipeline);

        AgentResult result = Agentspan.run(agent, "The history of the Internet");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
