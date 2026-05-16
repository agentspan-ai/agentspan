// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi01 — Basic OpenAI Agents SDK-shape agent.
//
// Simplest possible: a name + instructions + model wired through
// OpenAIAgent.From / Builder. The server's OpenAINormalizer compiles
// this into a Conductor workflow.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("greeter")
    .Instructions("You are a friendly assistant. Keep your responses concise and helpful.")
    .Model(Settings.LlmModel)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    agent,
    "Say hello and tell me a fun fact about the C# programming language.");
result.PrintResult();
