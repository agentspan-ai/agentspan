// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk01 — Basic Agent.
//
// The simplest Google ADK agent — defined via the GoogleADKAgent builder
// and executed on the Conductor runtime.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("greeter")
    .Model(Settings.LlmModel)
    .Instruction("You are a friendly assistant. Keep your responses concise and helpful.")
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent, "Say hello and tell me a fun fact about machine learning.");
Console.WriteLine($"agent completed with status: {result.Status}");
result.PrintResult();
