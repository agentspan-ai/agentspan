// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

/**
 * Example 06 — Sequential Pipeline
 *
 * <p>Demonstrates chaining agents into a sequential pipeline using {@link Agent#then(Agent)}.
 * Each agent's output becomes the next agent's input.
 */
public class Example06SequentialPipeline {

    public static void main(String[] args) {
        // Step 1: Researcher gathers information
        Agent researcher = Agent.builder()
            .name("researcher")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a researcher. Given a topic, provide 3-5 key facts and current trends. "
                + "Be concise and factual. Format as a numbered list.")
            .build();

        // Step 2: Writer turns research into an article
        Agent writer = Agent.builder()
            .name("writer")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a content writer. Given research findings, write a well-structured "
                + "2-3 paragraph article for a general audience. "
                + "Make it engaging and informative.")
            .build();

        // Step 3: Editor polishes the article
        Agent editor = Agent.builder()
            .name("editor")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an editor. Review and improve the provided article. "
                + "Fix grammar, improve clarity, and ensure it's publication-ready. "
                + "Add a compelling title at the beginning.")
            .build();

        // Chain into a sequential pipeline using .then()
        Agent contentPipeline = researcher.then(writer).then(editor);

        System.out.println("Pipeline: " + contentPipeline.getName());
        System.out.println("Sub-agents: " + contentPipeline.getAgents().size());

        AgentResult result = Agentspan.run(contentPipeline,
            "Write an article about the future of renewable energy");
        result.printResult();

        Agentspan.shutdown();
    }
}
