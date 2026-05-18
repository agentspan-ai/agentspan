// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 15 — Media tools (Image / Audio / Video): plan-level structure +
// end-to-end image generation via the OpenAI provider. Ports Python
// suite7 (test_suite7_media_tools.py).
//
// Plan-level checks verify the toolType field serialises to the
// expected Conductor task type (GENERATE_IMAGE / GENERATE_AUDIO /
// GENERATE_VIDEO). Runtime check exercises the actual OpenAI image
// generation pipeline; gated by OPENAI_API_KEY availability.

using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite15_MediaTools
{
    private readonly E2eFixture _fixture;

    public Suite15_MediaTools(E2eFixture fixture) => _fixture = fixture;

    // ── 15.1  Image tool serialises to generate_image toolType ───────────

    [SkippableFact]
    public async Task ImageTool_AppearsInPlanWithGenerateImageType()
    {
        _fixture.RequireServer();

        var agent = new Agent("s15_image_plan")
        {
            Model = Settings.LlmModel,
            Tools = [MediaTools.Image(
                name:        "generate_test_image",
                description: "Generate an image.",
                llmProvider: "openai",
                model:       "gpt-image-1")],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        Assert.NotNull(tools);

        var imageTools = tools!
            .Where(t => t?["toolType"]?.GetValue<string>() == "generate_image")
            .ToList();
        Assert.Single(imageTools);
        Assert.Equal("generate_test_image", imageTools[0]!["name"]?.GetValue<string>());
    }

    // ── 15.2  Audio tool serialises to generate_audio toolType ───────────

    [SkippableFact]
    public async Task AudioTool_AppearsInPlanWithGenerateAudioType()
    {
        _fixture.RequireServer();

        var agent = new Agent("s15_audio_plan")
        {
            Model = Settings.LlmModel,
            Tools = [MediaTools.Audio(
                name:        "generate_test_audio",
                description: "Generate audio.",
                llmProvider: "openai",
                model:       "tts-1")],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        Assert.NotNull(tools);

        var audioTools = tools!
            .Where(t => t?["toolType"]?.GetValue<string>() == "generate_audio")
            .ToList();
        Assert.Single(audioTools);
    }

    // ── 15.3  Video tool serialises to generate_video toolType ───────────

    [SkippableFact]
    public async Task VideoTool_AppearsInPlanWithGenerateVideoType()
    {
        _fixture.RequireServer();

        var agent = new Agent("s15_video_plan")
        {
            Model = Settings.LlmModel,
            Tools = [MediaTools.Video(
                name:        "generate_test_video",
                description: "Generate a video.",
                llmProvider: "openai",
                model:       "sora-2")],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        Assert.NotNull(tools);

        var videoTools = tools!
            .Where(t => t?["toolType"]?.GetValue<string>() == "generate_video")
            .ToList();
        Assert.Single(videoTools);
    }

    // ── 15.4  Multiple media tools coexist with distinct toolTypes ──────

    [SkippableFact]
    public async Task MediaTools_MultipleDistinctTypesInPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s15_multi_media")
        {
            Model = Settings.LlmModel,
            Tools =
            [
                MediaTools.Image(name: "img", description: "i", llmProvider: "openai", model: "gpt-image-1"),
                MediaTools.Audio(name: "aud", description: "a", llmProvider: "openai", model: "tts-1"),
                MediaTools.Video(name: "vid", description: "v", llmProvider: "openai", model: "sora-2"),
                MediaTools.Pdf(),
            ],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        Assert.NotNull(tools);

        var toolTypes = tools!
            .Select(t => t?["toolType"]?.GetValue<string>() ?? "")
            .ToList();
        Assert.Contains("generate_image", toolTypes);
        Assert.Contains("generate_audio", toolTypes);
        Assert.Contains("generate_video", toolTypes);
        Assert.Contains("generate_pdf", toolTypes);
    }

    // ── 15.5  Runtime: image generation completes via OpenAI ─────────────
    //
    // Mirrors Python's test_image_openai. Gated on OPENAI_API_KEY because
    // the GENERATE_IMAGE task calls the real OpenAI image API.

    [SkippableFact]
    public async Task ImageGeneration_OpenAI_TaskCompletes()
    {
        _fixture.RequireServer();
        Skip.If(string.IsNullOrEmpty(Environment.GetEnvironmentVariable("OPENAI_API_KEY")),
            "OPENAI_API_KEY not set — skipping live image generation test.");

        var agent = new Agent("s15_image_openai_rt")
        {
            Model        = Settings.LlmModel,
            Instructions = "You generate images. When asked, call generate_image with the user's prompt.",
            Tools        =
            [
                MediaTools.Image(
                    name:        "generate_image",
                    description: "Generate an image from a text prompt.",
                    llmProvider: "openai",
                    model:       "gpt-image-1"),
            ],
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(
            agent,
            "Generate an image of a single red apple on a white background.");

        Assert.True(result.IsSuccess, $"Agent run did not succeed: {result.Error}");
        Assert.NotNull(result.ExecutionId);

        var wf = await _fixture.FetchWorkflowAsync(result.ExecutionId!);
        var tasks = wf?["tasks"]?.AsArray();
        Assert.NotNull(tasks);

        var imgTask = tasks!.FirstOrDefault(t =>
        {
            var tt = t?["taskType"]?.GetValue<string>() ?? "";
            var tdn = t?["taskDefName"]?.GetValue<string>() ?? "";
            return tt.Contains("GENERATE_IMAGE") || tdn.Contains("generate_image");
        });

        Assert.NotNull(imgTask);
        // COMPLETED_WITH_ERRORS is acceptable: the OpenAI image API sometimes
        // returns soft errors (e.g., moderation warnings) while still producing
        // a valid image; Conductor surfaces this as COMPLETED_WITH_ERRORS.
        var status = imgTask!["status"]?.GetValue<string>();
        Assert.True(status is "COMPLETED" or "COMPLETED_WITH_ERRORS",
            $"GENERATE_IMAGE task status should be COMPLETED or COMPLETED_WITH_ERRORS, got '{status}'.");
    }
}
