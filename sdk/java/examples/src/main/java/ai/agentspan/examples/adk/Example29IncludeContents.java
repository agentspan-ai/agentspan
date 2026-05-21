// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;

/**
 * Example Adk 29 — Include Contents
 *
 * <p>Java port of <code>sdk/python/examples/adk/29_include_contents.py</code>.
 *
 * <p>Demonstrates: ADK's native {@code includeContents(NONE)} prevents a
 * sub-agent from inheriting the parent's conversation history.
 */
public class Example29IncludeContents {

    public static void main(String[] args) {
        // Sub-coordinator with include_contents="none" — no parent context.
        LlmAgent independentSummarizer = LlmAgent.builder()
            .name("independent_summarizer")
            .description("Summarizes text without inheriting the parent's conversation history.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a summarizer. Summarize any text given to you concisely.")
            .includeContents(LlmAgent.IncludeContents.NONE)
            .build();

        // Sub-coordinator that sees parent context (default).
        LlmAgent contextAwareHelper = LlmAgent.builder()
            .name("context_aware_helper")
            .description("Answers using the full parent conversation context.")
            .model(Settings.LLM_MODEL)
            .instruction("You are a helpful assistant that builds on prior conversation context.")
            .includeContents(LlmAgent.IncludeContents.DEFAULT)
            .build();

        LlmAgent coordinator = LlmAgent.builder()
            .name("coordinator")
            .description("Routes summarization to the independent summarizer and questions to the helper.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You coordinate tasks. Route summarization to independent_summarizer "
                + "and general questions to context_aware_helper.")
            .subAgents(independentSummarizer, contextAwareHelper)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Please summarize this: 'The quick brown fox jumps over the lazy dog. "
            + "This sentence contains every letter of the alphabet and is commonly "
            + "used for typography testing.'");
        result.printResult();

        Agentspan.shutdown();
    }
}
