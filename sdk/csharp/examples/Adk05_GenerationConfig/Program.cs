// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk05 — Generation Config.
//
// Temperature and output control. The Python original uses ADK's
// generate_content_config dict for tuning.
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose generation config directly; we document the intent in the
// instruction and rely on server defaults.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var factualAgent = GoogleADKAgent.Builder()
    .Name("fact_checker")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a precise fact-checker. Provide accurate, well-sourced " +
        "answers. Be concise and avoid speculation.")
    .Build();

var creativeAgent = GoogleADKAgent.Builder()
    .Name("storyteller")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an imaginative storyteller. Create vivid, engaging " +
        "narratives with rich descriptions and unexpected twists.")
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

Console.WriteLine("=== Factual Agent (temp=0.1) ===");
var factual = await runtime.RunAsync(factualAgent, "What is the speed of light in a vacuum?");
factual.PrintResult();

Console.WriteLine("\n=== Creative Agent (temp=0.9) ===");
var creative = await runtime.RunAsync(creativeAgent,
    "Write a two-sentence story about a cat who discovered a hidden library.");
creative.PrintResult();
