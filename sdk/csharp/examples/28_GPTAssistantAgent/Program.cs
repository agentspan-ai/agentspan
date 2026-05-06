// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// GPTAssistantAgent — wrap OpenAI Assistants API as an Agentspan agent.
//
// GPTAssistantAgent.Create() builds an Agent whose internal tool
// creates an OpenAI Thread, posts a message, polls the Run to completion,
// and returns the assistant's reply.
//
// Two modes:
//   1. Create a new assistant on the fly (this example)
//   2. Use an existing assistant by ID
//
// Requirements:
//   - OPENAI_API_KEY in environment
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Example 1: Create assistant on the fly ───────────────────────────

var dataAnalyst = GPTAssistantAgent.Create(
    name:         "data_analyst",
    model:        Settings.LlmModel,
    instructions: "You are a data analyst. Use the code interpreter to analyze data and perform calculations.",
    openAiTools:  [new Dictionary<string, object> { ["type"] = "code_interpreter" }]);

// ── Example 2: Use an existing assistant ─────────────────────────────

// If you already have an assistant created in the OpenAI dashboard:
// var existingAssistant = GPTAssistantAgent.FromExistingAssistant(
//     name:        "my_assistant",
//     assistantId: "asst_abc123def456");

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- GPT Assistant with Code Interpreter ---");
var result = await runtime.RunAsync(
    dataAnalyst,
    "Calculate the standard deviation of these numbers: 4, 8, 15, 16, 23, 42");

result.PrintResult();
