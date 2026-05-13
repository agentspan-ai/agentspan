// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Multimodal Agent — analyze images with vision-capable models.
//
// Pass image URLs via the media parameter on runtime.RunAsync().
// The server includes them in the LLM ChatMessage media field,
// enabling vision-capable models (GPT-4o, Gemini, Claude) to see them.
//
// Supported media types:
//   - Images: JPEG, PNG, GIF, WebP (URL or data URI)
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (must be a vision model, e.g. openai/gpt-4o)

using Agentspan;
using Agentspan.Examples;

// Sample public images for demonstration
const string sampleImage  = "https://orkes.io/Home-Page-Prompt-to-Workflow-1.png";
const string sampleImage2 = "https://orkes.io/icons/hero-section-workflow_updated.png";

await using var runtime = new AgentRuntime();

// ── 1. Single image analysis ──────────────────────────────────────────

var visionAgent = new Agent("vision_analyst")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a visual analysis expert. Describe images in detail, " +
        "noting composition, colors, subjects, and any text visible.",
};

Console.WriteLine("=== Single Image Analysis ===");
var result = await runtime.RunAsync(
    visionAgent,
    "What do you see in this image? Describe it in detail.",
    media: [sampleImage]);
result.PrintResult();

// ── 2. Image analysis with tools ─────────────────────────────────────

var visionWithTools = new Agent("vision_researcher")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new VisionTools()),
    Instructions =
        "You are a visual research assistant. Analyze images, search for " +
        "similar ones, and save your findings. Always save your analysis.",
};

Console.WriteLine("\n=== Image Analysis with Tools ===");
var result2 = await runtime.RunAsync(
    visionWithTools,
    "Analyze this image, search for similar ones, and save your findings.",
    media: [sampleImage]);
result2.PrintResult();

// ── 3. Compare multiple images ────────────────────────────────────────

var comparator = new Agent("image_comparator")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are an image comparison specialist. When given multiple images, " +
        "compare and contrast them: similarities, differences, style, and subject matter.",
};

Console.WriteLine("\n=== Multi-Image Comparison ===");
var result3 = await runtime.RunAsync(
    comparator,
    "Compare these two images. What are the key differences?",
    media: [sampleImage, sampleImage2]);
result3.PrintResult();

// ── 4. Multi-agent creative pipeline ─────────────────────────────────

var describer = new Agent("describer")
{
    Model        = Settings.LlmModel,
    Instructions = "Describe the image in 2-3 vivid sentences.",
};

var storyteller = new Agent("storyteller")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You receive an image description. Write a short creative " +
        "story (3-4 sentences) inspired by it.",
};

var creativePipeline = describer >> storyteller;

Console.WriteLine("\n=== Creative Pipeline (describe → story) ===");
var result4 = await runtime.RunAsync(
    creativePipeline,
    "Create a story inspired by this image.",
    media: [sampleImage2]);
result4.PrintResult();

// ── Vision tools ──────────────────────────────────────────────────────

internal sealed class VisionTools
{
    [Tool("Search for similar images based on a description.")]
    public string SearchSimilar(string description)
        => $"Found 3 similar images matching: '{description}'";

    [Tool("Save an image analysis report.")]
    public string SaveAnalysis(string title, string analysis)
        => $"Saved analysis '{title}': {analysis[..Math.Min(100, analysis.Length)]}...";
}
