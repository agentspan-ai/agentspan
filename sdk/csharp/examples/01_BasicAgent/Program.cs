// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Basic Agent — 5-line hello world.
//
// Demonstrates the simplest possible agent: define an agent, call
// runtime.RunAsync(), and print the result.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional, defaults to openai/gpt-4o-mini)

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("greeter")
{
    Model = Settings.LlmModel,
    Instructions = "You are a friendly assistant. Keep responses brief.",
};

var prompt = "Say hello and tell me a fun fact about C#.";

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, prompt);
result.PrintResult();
