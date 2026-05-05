// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sequential Pipeline with Stage-Level Tools — movie production pipeline.
//
// Demonstrates the >> operator where EACH sub-agent in the pipeline
// has its own specialized tools. Each stage builds on the previous one:
//
//   concept_developer >> scriptwriter >> visual_director
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Pipeline stages, each with their own tools ────────────────────────

var conceptDeveloper = new Agent("concept_developer")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a creative producer. Use create_concept to define the film concept.",
    Tools        = ToolRegistry.FromInstance(new ConceptTools()),
};

var scriptwriter = new Agent("scriptwriter")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a screenwriter. Use write_scene to draft key scenes from the concept.",
    Tools        = ToolRegistry.FromInstance(new ScriptTools()),
};

var visualDirector = new Agent("visual_director")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a visual director. Use describe_visual to add cinematography notes to each scene.",
    Tools        = ToolRegistry.FromInstance(new VisualTools()),
};

// ── Sequential pipeline using >> ─────────────────────────────────────

var pipeline = conceptDeveloper >> scriptwriter >> visualDirector;

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "Create a short film about an AI that learns to paint.");

result.PrintResult();

// ── Tool classes ──────────────────────────────────────────────────────

internal sealed class ConceptTools
{
    [Tool("Create a movie concept document with title, genre, and logline.")]
    public Dictionary<string, object> CreateConcept(string title, string genre, string logline)
        => new() { ["concept"] = new Dictionary<string, object> { ["title"] = title, ["genre"] = genre, ["logline"] = logline, ["status"] = "approved" } };
}

internal sealed class ScriptTools
{
    [Tool("Write a single scene for the script.")]
    public Dictionary<string, object> WriteScene(int sceneNumber, string location, string action, string dialogue = "")
    {
        var scene = new Dictionary<string, object> { ["scene"] = sceneNumber, ["location"] = location, ["action"] = action };
        if (!string.IsNullOrEmpty(dialogue)) scene["dialogue"] = dialogue;
        return new() { ["scene"] = scene };
    }
}

internal sealed class VisualTools
{
    [Tool("Describe visual/cinematography direction for a scene.")]
    public Dictionary<string, object> DescribeVisual(int sceneNumber, string shotType, string description)
        => new() { ["visual"] = new Dictionary<string, object> { ["scene"] = sceneNumber, ["shot_type"] = shotType, ["description"] = description } };
}
