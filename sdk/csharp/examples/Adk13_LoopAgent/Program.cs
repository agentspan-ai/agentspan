// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk13 — Loop Agent.
//
// Python's LoopAgent repeats sub-agents for iterative refinement (up to
// 3 iterations of write -> critique). We model the same intent through
// a coordinator instructed to loop write/critique cycles.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var writer = GoogleADKAgent.Builder()
    .Name("draft_writer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a writer. Write or revise a short haiku (3 lines: 5-7-5 syllables) " +
        "about the given topic. If there is feedback from a previous critique in the conversation, " +
        "incorporate it. Output only the haiku, nothing else.")
    .Build();

var critic = GoogleADKAgent.Builder()
    .Name("critic")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a poetry critic. Review the haiku from the writer. " +
        "Check: (1) Does it follow 5-7-5 syllable structure? " +
        "(2) Is the imagery vivid? (3) Is there a seasonal or nature element? " +
        "Provide 1-2 sentences of constructive feedback for improvement.")
    .Build();

var refinementLoop = GoogleADKAgent.Builder()
    .Name("refinement_loop")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate an iterative refinement loop. Run the cycle " +
        "[draft_writer -> critic] up to 3 times (max_iterations=3), " +
        "feeding the critic's feedback back to the writer each pass. " +
        "Return the final polished haiku.")
    .SubAgents(writer, critic)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(refinementLoop, "Write a haiku about autumn leaves");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();
