// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk11 — Sequential Agent Pipeline.
//
// Python's SequentialAgent runs sub-agents in fixed order with outputs
// flowing to the next. We model the same intent through a coordinator
// with sub-agents and instructions that dictate the execution order.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var researcher = GoogleADKAgent.Builder()
    .Name("researcher")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a research assistant. Given the user's topic, " +
        "provide 3 key facts about it in a numbered list. Be concise.")
    .Build();

var writer = GoogleADKAgent.Builder()
    .Name("writer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a skilled writer. Take the research provided in the conversation " +
        "and write a single engaging paragraph summarizing the key points. " +
        "Keep it under 100 words.")
    .Build();

var editor = GoogleADKAgent.Builder()
    .Name("editor")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an editor. Review the paragraph from the writer and improve it. " +
        "Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph.")
    .Build();

var pipeline = GoogleADKAgent.Builder()
    .Name("content_pipeline")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a content pipeline. Execute the steps in this order:\n" +
        "1. researcher gathers 3 key facts\n" +
        "2. writer composes a paragraph from those facts\n" +
        "3. editor polishes the paragraph\n" +
        "Return the editor's final paragraph.")
    .SubAgents(researcher, writer, editor)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(pipeline, "The history of the Internet");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();
