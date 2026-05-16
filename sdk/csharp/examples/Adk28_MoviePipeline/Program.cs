// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk28 — Short Movie Pipeline.
//
// A SequentialAgent-style pipeline with 5 stages
// (concept -> script -> visuals -> audio -> assembly).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var conceptDeveloper = GoogleADKAgent.Builder()
    .Name("concept_developer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a creative director. Develop a concept for a short film " +
        "based on the given theme. Use create_concept to document the " +
        "title, genre, and logline. Keep it concise and compelling.")
    .Tools(new ConceptTools())
    .Build();

var scriptwriter = GoogleADKAgent.Builder()
    .Name("scriptwriter")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a scriptwriter. Based on the concept from the previous " +
        "stage, write 3 short scenes using write_scene for each. " +
        "Include location, action, and brief dialogue.")
    .Tools(new ScriptTools())
    .Build();

var visualDirector = GoogleADKAgent.Builder()
    .Name("visual_director")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a visual director. For each scene written by the " +
        "scriptwriter, use describe_visual to specify camera shots, " +
        "lighting, and visual mood. Create one visual spec per scene.")
    .Tools(new VisualTools())
    .Build();

var audioDesigner = GoogleADKAgent.Builder()
    .Name("audio_designer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an audio designer. For each scene, use specify_audio " +
        "to define the music mood and key sound effects. Match the " +
        "audio to the visual mood described by the visual director.")
    .Tools(new AudioTools())
    .Build();

var producer = GoogleADKAgent.Builder()
    .Name("producer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are the producer. Review all previous stages and use " +
        "assemble_production to create final production notes. " +
        "Summarize the complete short film with all creative elements.")
    .Tools(new ProducerTools())
    .Build();

var moviePipeline = GoogleADKAgent.Builder()
    .Name("short_movie_pipeline")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a short-movie production pipeline. Run the stages in order: " +
        "concept_developer -> scriptwriter -> visual_director -> audio_designer -> producer.")
    .SubAgents(conceptDeveloper, scriptwriter, visualDirector, audioDesigner, producer)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(moviePipeline,
    "Create a 3-scene short film about a robot discovering music " +
    "for the first time in a post-apocalyptic world.");
result.PrintResult();

internal sealed class ConceptTools
{
    [Tool(Name = "create_concept", Description = "Create a movie concept document.")]
    public Dictionary<string, object> CreateConcept(string title, string genre, string logline)
        => new()
        {
            ["concept"] = new Dictionary<string, object>
            {
                ["title"]   = title,
                ["genre"]   = genre,
                ["logline"] = logline,
                ["status"]  = "approved",
            },
        };
}

internal sealed class ScriptTools
{
    [Tool(Name = "write_scene", Description = "Write a single scene for the script.")]
    public Dictionary<string, object> WriteScene(int scene_number, string location, string action, string dialogue)
    {
        var scene = new Dictionary<string, object>
        {
            ["scene"]    = scene_number,
            ["location"] = location,
            ["action"]   = action,
        };
        if (!string.IsNullOrEmpty(dialogue)) scene["dialogue"] = dialogue;
        return new Dictionary<string, object> { ["scene"] = scene };
    }
}

internal sealed class VisualTools
{
    [Tool(Name = "describe_visual", Description = "Describe visual direction for a scene.")]
    public Dictionary<string, object> DescribeVisual(int scene_number, string shot_type, string description)
        => new()
        {
            ["visual"] = new Dictionary<string, object>
            {
                ["scene"]       = scene_number,
                ["shot_type"]   = shot_type,
                ["description"] = description,
            },
        };
}

internal sealed class AudioTools
{
    [Tool(Name = "specify_audio", Description = "Specify audio direction for a scene.")]
    public Dictionary<string, object> SpecifyAudio(int scene_number, string music_mood, string sound_effects)
        => new()
        {
            ["audio"] = new Dictionary<string, object>
            {
                ["scene"]         = scene_number,
                ["music_mood"]    = music_mood,
                ["sound_effects"] = sound_effects,
            },
        };
}

internal sealed class ProducerTools
{
    [Tool(Name = "assemble_production", Description = "Assemble final production notes.")]
    public Dictionary<string, object> AssembleProduction(string title, int total_scenes, string estimated_runtime)
        => new()
        {
            ["production"] = new Dictionary<string, object>
            {
                ["title"]             = title,
                ["total_scenes"]      = total_scenes,
                ["estimated_runtime"] = estimated_runtime,
                ["status"]            = "ready_for_production",
            },
        };
}
