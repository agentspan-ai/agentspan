// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Skills — load an agentskills.io skill directory as an Agentspan Agent.
//
// Skill scripts become worker tools, and resources under references/,
// examples/, assets/, plus root resource files, are available through the
// generated read_skill_file tool.
//
// Usage:
//   AGENTSPAN_SERVER_URL=http://localhost:6767/api \
//   AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini \
//   dotnet run --project sdk/csharp/examples/91_Skills/Example91Skills.csproj \
//     -- /path/to/skill "Review this repository"

using Agentspan;
using Agentspan.Examples;

var skillPath = args.Length > 0
    ? args[0]
    : System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        ".claude",
        "skills",
        "dg");
var prompt = args.Length > 1
    ? args[1]
    : "Run this skill against the current request and return a concise result.";

if (!File.Exists(System.IO.Path.Combine(skillPath, "SKILL.md")))
    throw new ArgumentException($"Expected a skill directory containing SKILL.md: {skillPath}");

var skillAgent = Skill.Load(
    skillPath,
    Settings.LlmModel,
    searchPath: [System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        ".agents",
        "skills")]);

await using var runtime = new AgentRuntime();
var direct = await runtime.RunAsync(skillAgent, prompt);
direct.PrintResult();

var parent = new Agent("skill_tool_manager_91")
{
    Model        = Settings.LlmModel,
    Instructions = "Use the wrapped skill tool for the user request, then return the skill result.",
    Tools        = [AgentTool.Create(skillAgent, description: "Run the loaded skill")],
    MaxTurns     = 4,
};

var viaTool = await runtime.RunAsync(parent, prompt);
viaTool.PrintResult();
