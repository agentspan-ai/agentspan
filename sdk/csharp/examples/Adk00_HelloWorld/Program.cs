// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk00 — Hello World.
//
// Minimal Google ADK greeting agent — no tools, no structured output,
// one turn. The simplest possible ADK agent.
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
    .Instruction("You are a friendly greeter. Reply with a warm hello and one fun fact.")
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent, "Say hello!");
result.PrintResult();
