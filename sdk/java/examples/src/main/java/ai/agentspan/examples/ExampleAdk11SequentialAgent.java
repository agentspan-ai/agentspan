// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 11 — Sequential Agent Pipeline
 *
 * <p>Java port of <code>sdk/python/examples/adk/11_sequential_agent.py</code>.
 *
 * <p>Demonstrates: Python's {@code SequentialAgent} runs sub-agents in fixed
 * order with outputs flowing to the next. Java's {@link GoogleADKAgent} models
 * the same intent through a coordinator with sub-agents and instructions that
 * dictate the execution order.
 */
public class ExampleAdk11SequentialAgent {

    public static void main(String[] args) {
        // Step 1: Research agent gathers facts
        Agent researcher = GoogleADKAgent.builder()
            .name("researcher")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a research assistant. Given the user's topic, "
                + "provide 3 key facts about it in a numbered list. Be concise.")
            .build();

        // Step 2: Writer agent takes the research and writes a summary
        Agent writer = GoogleADKAgent.builder()
            .name("writer")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a skilled writer. Take the research provided in the conversation "
                + "and write a single engaging paragraph summarizing the key points. "
                + "Keep it under 100 words.")
            .build();

        // Step 3: Editor agent polishes the summary
        Agent editor = GoogleADKAgent.builder()
            .name("editor")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an editor. Review the paragraph from the writer and improve it. "
                + "Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph.")
            .build();

        // Pipeline: researcher → writer → editor
        Agent pipeline = GoogleADKAgent.builder()
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

        AgentResult result = Agentspan.run(pipeline, "The history of the Internet");
        System.out.println("Status: " + result.getStatus());
        result.printResult();

        Agentspan.shutdown();
    }
}
