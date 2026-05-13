// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Media Generation Agent — generate images, audio, and video using AI models.
//
// Demonstrates Conductor's built-in media generation system tasks
// (GENERATE_IMAGE, GENERATE_AUDIO, GENERATE_VIDEO) exposed as native agent
// tools via MediaTools.Image(), MediaTools.Audio(), and MediaTools.Video().
// These are server-side tools — no worker process is needed.
//
// Requirements:
//   - Conductor server with OpenAI integration configured
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Media generation tools (server-side, no worker needed) ────

var genImage = MediaTools.Image(
    name:        "generate_image",
    description: "Generate an image from a text description using DALL-E 3.",
    llmProvider: "openai",
    model:       "dall-e-3");

var genAudio = MediaTools.Audio(
    name:        "text_to_speech",
    description: "Convert text to natural-sounding speech audio using OpenAI TTS.",
    llmProvider: "openai",
    model:       "tts-1");

var genVideo = MediaTools.Video(
    name:        "generate_video",
    description: "Generate a short video clip from a text description using OpenAI Sora.",
    llmProvider: "openai",
    model:       "sora-2",
    extra:       new() { ["size"] = "1280x720", ["n"] = 1 });

// ── Media orchestrator ────────────────────────────────────────

var mediaAgent = new Agent("media_generator_40")
{
    Model        = Settings.LlmModel,
    Tools        = [genImage, genAudio, genVideo],
    Instructions =
        "You are a creative media generation assistant. You can generate:\n\n" +
        "1. **Images** — from text descriptions using DALL-E 3.\n" +
        "2. **Audio** — text-to-speech using OpenAI TTS " +
        "(voices: alloy, echo, fable, onyx, nova, shimmer).\n" +
        "3. **Video** — short video clips from text using OpenAI Sora.\n\n" +
        "IMPORTANT: Image prompts MUST be under 950 characters.\n" +
        "Call the appropriate tool once and present the result.",
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    mediaAgent,
    "Create an image of a serene Japanese garden with a koi pond " +
    "at sunset, cherry blossoms falling gently. Use vivid style.");

result.PrintResult();
