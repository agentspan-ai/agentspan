// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 32 — Nested Strategies
 *
 * <p>Java port of <code>sdk/python/examples/adk/32_nested_strategies.py</code>.
 *
 * <p>Demonstrates: composing agent strategies — Python uses
 * {@code SequentialAgent} containing a {@code ParallelAgent} research phase
 * followed by a summarizer. The Java port models this through nested
 * {@link LlmAgent} coordinators whose instructions express the parallel/
 * sequential intent.
 */
public class Example32NestedStrategies {

    public static void main(String[] args) {
        // ── Parallel research agents ────────────────────────────────────
        LlmAgent marketAnalyst = LlmAgent.builder()
            .name("market_analyst")
            .description("Provides a concise market-size, growth, and competitive analysis.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a market analyst. Analyze the market size, growth rate, "
                + "and key players for the given topic. Be concise (3-4 bullet points).")
            .build();

        LlmAgent riskAnalyst = LlmAgent.builder()
            .name("risk_analyst")
            .description("Identifies the top regulatory, technical, and competitive risks.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a risk analyst. Identify the top 3 risks: regulatory, "
                + "technical, and competitive. Be concise.")
            .build();

        LlmAgent parallelResearch = LlmAgent.builder()
            .name("research_phase")
            .description("Runs the market and risk analysts concurrently and aggregates their output.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate a parallel research phase. Dispatch the topic to
                market_analyst and risk_analyst concurrently, then aggregate
                their outputs.
                """)
            .subAgents(marketAnalyst, riskAnalyst)
            .build();

        // ── Summarizer ───────────────────────────────────────────────────
        LlmAgent summarizer = LlmAgent.builder()
            .name("summarizer")
            .description("Synthesizes the parallel research into a one-paragraph executive briefing.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are an executive briefing writer. Synthesize the market analysis "
                + "and risk assessment into a concise executive summary (1 paragraph).")
            .build();

        // ── Pipeline: parallel → sequential ──────────────────────────────
        LlmAgent pipeline = LlmAgent.builder()
            .name("analysis_pipeline")
            .description("Nested strategy: parallel research phase followed by a sequential summarizer.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate an analysis pipeline. First run research_phase "
                + "(parallel research), then summarizer.")
            .subAgents(parallelResearch, summarizer)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "Launching an AI-powered healthcare diagnostics tool in the US");
        result.printResult();

        Agentspan.shutdown();
    }
}
