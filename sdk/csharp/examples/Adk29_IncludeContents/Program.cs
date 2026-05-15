// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk29 — Include Contents.
//
// ADK's include_contents="none" prevents a sub-agent from inheriting
// the parent's conversation history.
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose include_contents directly; the intent is documented in
// each agent's instruction.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var independentSummarizer = GoogleADKAgent.Builder()
    .Name("independent_summarizer")
    .Model(Settings.LlmModel)
    .Instruction("You are a summarizer. Summarize any text given to you concisely.")
    .Build();

var contextAwareHelper = GoogleADKAgent.Builder()
    .Name("context_aware_helper")
    .Model(Settings.LlmModel)
    .Instruction("You are a helpful assistant that builds on prior conversation context.")
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You coordinate tasks. Route summarization to independent_summarizer " +
        "and general questions to context_aware_helper.")
    .SubAgents(independentSummarizer, contextAwareHelper)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Please summarize this: 'The quick brown fox jumps over the lazy dog. " +
    "This sentence contains every letter of the alphabet and is commonly " +
    "used for typography testing.'");
result.PrintResult();
