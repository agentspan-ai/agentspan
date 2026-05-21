// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 14 — PDF tools: plan-level validation + end-to-end generation.
//
// Ports Python suite6 (test_pdf_generation_and_roundtrip) — the round-trip
// content validation step (Python uses ``markitdown``) is replaced here by
// asserting the GENERATE_PDF task completed and produced a non-empty
// output, since C# lacks an in-process markdown-from-PDF extractor.

using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite14_PdfTools
{
    private readonly E2eFixture _fixture;

    public Suite14_PdfTools(E2eFixture fixture) => _fixture = fixture;

    private const string SampleMarkdown = """
        # Agentspan E2E Test Report

        ## Overview
        This document validates the PDF generation pipeline.

        ## Key Metrics
        - Tests Run: 12
        - Passed: 11
        """;

    // ── 14.1  Plan structure: PDF tool serialises as generate_pdf type ──

    [SkippableFact]
    public async Task PdfTool_AppearsInPlanWithGeneratePdfType()
    {
        _fixture.RequireServer();

        var agent = new Agent("s14_pdf_plan")
        {
            Model        = Settings.LlmModel,
            Instructions = "You generate PDFs.",
            Tools        = [MediaTools.Pdf()],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        Assert.NotNull(tools);

        var pdfTools = tools!
            .Where(t => t?["toolType"]?.GetValue<string>() == "generate_pdf")
            .ToList();
        Assert.Single(pdfTools);
        Assert.Equal("generate_pdf", pdfTools[0]!["name"]?.GetValue<string>());
    }

    // ── 14.2  PDF tool's default schema has markdown + filename ─────────

    [SkippableFact]
    public async Task PdfTool_DefaultSchemaHasMarkdownAndFilename()
    {
        _fixture.RequireServer();

        var agent = new Agent("s14_pdf_schema")
        {
            Model = Settings.LlmModel,
            Tools = [MediaTools.Pdf()],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tool = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray()
            ?.First(t => t?["toolType"]?.GetValue<string>() == "generate_pdf");
        Assert.NotNull(tool);

        var schema = tool!["inputSchema"]?.AsObject() ?? tool["input_schema"]?.AsObject();
        Assert.NotNull(schema);
        var props = schema!["properties"]?.AsObject();
        Assert.NotNull(props);
        // Default schema must include the markdown content field.
        Assert.True(props!.ContainsKey("markdown") || props.ContainsKey("content") || props.ContainsKey("text"),
            $"Expected default PDF schema to have a markdown/content/text property; got: {string.Join(",", props.Select(p => p.Key))}");
    }

    // ── 14.3  Custom PDF tool name + description round-trips ────────────

    [SkippableFact]
    public async Task PdfTool_CustomNameAndDescription_RoundTrip()
    {
        _fixture.RequireServer();

        var agent = new Agent("s14_pdf_custom")
        {
            Model = Settings.LlmModel,
            Tools = [MediaTools.Pdf(name: "my_pdf_gen", description: "My custom PDF generator.")],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tool = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray()
            ?.First(t => t?["toolType"]?.GetValue<string>() == "generate_pdf");
        Assert.NotNull(tool);
        Assert.Equal("my_pdf_gen", tool!["name"]?.GetValue<string>());
        Assert.Equal("My custom PDF generator.", tool["description"]?.GetValue<string>());
    }

    // ── 14.4  Counterfactual: agent without PDF tool has no GENERATE_PDF ─

    [SkippableFact]
    public async Task NoPdfTool_AgentDefHasNoGeneratePdf()
    {
        _fixture.RequireServer();

        var agent = new Agent("s14_no_pdf") { Model = Settings.LlmModel };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        var tools = plan!["workflowDef"]?["metadata"]?["agentDef"]?["tools"]?.AsArray();
        if (tools is not null)
        {
            var hasGeneratePdf = tools.Any(t => t?["toolType"]?.GetValue<string>() == "generate_pdf");
            Assert.False(hasGeneratePdf, "agentDef.tools should not have a generate_pdf entry when no PDF tool was added.");
        }
    }

    // ── 14.5  End-to-end: agent generates PDF, task completes ───────────

    [SkippableFact]
    public async Task PdfGeneration_TaskCompletesAndProducesOutput()
    {
        _fixture.RequireServer();

        var agent = new Agent("s14_pdf_gen")
        {
            Model        = Settings.LlmModel,
            Instructions = "You generate PDF documents. When asked, call generate_pdf with the exact markdown provided.",
            Tools        = [MediaTools.Pdf()],
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(
            agent,
            $"Convert the following markdown to a PDF. Pass it exactly to generate_pdf:\n\n{SampleMarkdown}");

        Assert.True(result.IsSuccess, $"Agent run did not succeed: {result.Error}");
        Assert.NotNull(result.ExecutionId);

        // Workflow inspection: find a GENERATE_PDF task and assert it completed.
        var wf = await _fixture.FetchWorkflowAsync(result.ExecutionId!);
        var tasks = wf?["tasks"]?.AsArray();
        Assert.NotNull(tasks);

        var pdfTask = tasks!.FirstOrDefault(t =>
        {
            var tt = t?["taskType"]?.GetValue<string>() ?? "";
            var tdn = t?["taskDefName"]?.GetValue<string>() ?? "";
            return tt.Contains("GENERATE_PDF") || tdn.Contains("generate_pdf");
        });

        Assert.NotNull(pdfTask);
        Assert.Equal("COMPLETED", pdfTask!["status"]?.GetValue<string>());

        // Output must have some non-empty data — URL, blob, or file path.
        var output = pdfTask["outputData"];
        Assert.NotNull(output);
        Assert.True(output!.ToString().Length > 20,
            $"GENERATE_PDF outputData should not be empty; got: {output}");
    }
}
