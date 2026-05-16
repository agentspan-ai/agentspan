// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk03 — Structured Output.
//
// Enforced JSON schema response via ADK's output_schema. The .OutputType("Recipe")
// hook maps to AgentConfig.outputType server-side.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("recipe_generator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a professional chef assistant. When asked for a recipe, " +
        "provide a complete, well-structured recipe with precise measurements, " +
        "clear step-by-step instructions, and accurate timing.")
    .OutputType("Recipe")
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent, "Give me a recipe for classic Italian carbonara pasta.");
result.PrintResult();
