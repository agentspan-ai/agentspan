// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;

/**
 * Example 15 — Agent Discussion (round-robin debate)
 *
 * <p>Demonstrates {@code Strategy.ROUND_ROBIN} where agents take turns in
 * a fixed rotation. An optimist and skeptic debate a topic across 6 turns
 * (3 rounds each), then a summarizer distills the key points.
 *
 * <pre>
 * discussion (ROUND_ROBIN, 6 turns)
 *   optimist → skeptic → optimist → skeptic → optimist → skeptic
 * └── summarizer (receives full transcript)
 * </pre>
 */
public class Example15AgentDiscussion {

    public static void main(String[] args) {
        // ── Discussion participants ────────────────────────────────────────

        Agent optimist = Agent.builder()
            .name("optimist")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are an optimistic technologist debating a topic. "
                + "Argue FOR the topic. Keep your response to 2-3 concise paragraphs. "
                + "Acknowledge the other side's points before making your case.")
            .build();

        Agent skeptic = Agent.builder()
            .name("skeptic")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a thoughtful skeptic debating a topic. "
                + "Raise concerns and argue AGAINST the topic. "
                + "Keep your response to 2-3 concise paragraphs. "
                + "Acknowledge the other side's points before making your case.")
            .build();

        // ── Round-robin discussion: 6 turns (3 rounds of back-and-forth) ──

        Agent discussion = Agent.builder()
            .name("discussion")
            .model(Settings.LLM_MODEL)
            .agents(optimist, skeptic)
            .strategy(Strategy.ROUND_ROBIN)
            .maxTurns(6)
            .build();

        // ── Summarizer ─────────────────────────────────────────────────────

        Agent summarizer = Agent.builder()
            .name("summarizer_15")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a neutral moderator. You have just observed a debate "
                + "between an optimist and a skeptic. Summarize the key arguments "
                + "from both sides and provide a balanced conclusion. "
                + "Structure your response with: Key Arguments For, "
                + "Key Arguments Against, and Balanced Conclusion.")
            .build();

        // ── Pipeline: discussion → summary ─────────────────────────────────

        Agent pipeline = Agent.builder()
            .name("debate_pipeline")
            .model(Settings.LLM_MODEL)
            .agents(discussion, summarizer)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Should AI agents be allowed to autonomously make financial decisions for individuals?");
        result.printResult();

        Agentspan.shutdown();
    }
}
