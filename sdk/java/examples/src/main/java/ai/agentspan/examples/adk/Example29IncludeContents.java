// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

/**
 * Example Adk 29 — Include Contents
 *
 * <p>Java port of <code>sdk/python/examples/adk/29_include_contents.py</code>.
 *
 * <p>Demonstrates: ADK's {@code include_contents="none"} prevents a sub-agent
 * from inheriting the parent's conversation history. The Java
 * {@link GoogleADKAgent} builder does not expose include_contents directly;
 * the intent is documented in each agent's instruction.
 */
public class Example29IncludeContents {

    public static void main(String[] args) {
        // Sub-agent that would normally have include_contents="none" — no parent context.
        Agent independentSummarizer = GoogleADKAgent.builder()
            .name("independent_summarizer")
            .model(Settings.LLM_MODEL)
            .instruction("You are a summarizer. Summarize any text given to you concisely.")
            .build();

        // Sub-agent that sees parent context (default).
        Agent contextAwareHelper = GoogleADKAgent.builder()
            .name("context_aware_helper")
            .model(Settings.LLM_MODEL)
            .instruction("You are a helpful assistant that builds on prior conversation context.")
            .build();

        Agent coordinator = GoogleADKAgent.builder()
            .name("coordinator")
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
