// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 16 — Plan-Execute (PAC/PAE) with cross-step Refs.
//
// Deterministic tests for the typed Plan / Step / Op / Ref builders:
//   - Ref("step_id") wires the whole output of an upstream step into a
//     downstream step's args (no JSON path, no field selection).
//   - Two Refs in the same args map resolve independently.
//
// The planner sub-agent is built but its output is discarded by the
// static-plan path (RunAsync(harness, prompt, plan: plan)). All
// assertions are algorithmic — per CLAUDE.md, we never use LLM output
// for validation.

using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;
using Agentspan.Plans;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite16_PlanExecuteRefs
{
    private readonly E2eFixture _fixture;

    public Suite16_PlanExecuteRefs(E2eFixture fixture) => _fixture = fixture;

    // ── Tool host ───────────────────────────────────────────────────────

    internal sealed class S16Tools
    {
        [Tool("Step A — emit a known record.")]
        public Dictionary<string, object> S16Produce(string record_id) => new()
        {
            ["record_id"] = record_id,
            ["value"] = 42,
            ["tags"] = new[] { "alpha", "beta" },
        };

        [Tool("Step B — read Step A via Ref.")]
        public Dictionary<string, object?> S16Enrich(JsonElement record)
        {
            var dict = JsonSerializer.Deserialize<Dictionary<string, object?>>(record.GetRawText())!;
            var value = ((JsonElement)dict["value"]!).GetInt32();
            dict["value_squared"] = value * value;
            return dict;
        }

        [Tool("Step C — read BOTH upstream steps.")]
        public Dictionary<string, object?> S16Report(JsonElement record, JsonElement enriched) => new()
        {
            ["id"] = record.GetProperty("record_id").GetString(),
            ["original_value"] = record.GetProperty("value").GetInt32(),
            ["squared"] = enriched.GetProperty("value_squared").GetInt32(),
            ["tags_joined"] = string.Join(
                ", ",
                record.GetProperty("tags").EnumerateArray().Select(e => e.GetString()!)),
        };
    }

    // ── Helpers ─────────────────────────────────────────────────────────

    private Agent BuildRefsHarness()
    {
        var planner = new Agent("s16_refs_planner")
        {
            Model = Settings.LlmModel,
            Instructions = "(planner unused; static plan supplied)",
        };
        return new Agent("s16_refs_harness")
        {
            Model = Settings.LlmModel,
            Strategy = Strategy.PlanExecute,
            Planner = planner,
            Tools = ToolRegistry.FromInstance(new S16Tools()),
        };
    }

    private async Task<Dictionary<string, JsonNode?>> FetchStepOutputsAsync(string executionId)
    {
        var parent = await _fixture.FetchWorkflowAsync(executionId);
        string? subId = null;
        foreach (var t in parent?["tasks"]?.AsArray() ?? new JsonArray())
        {
            var refName = t?["referenceTaskName"]?.GetValue<string>() ?? "";
            if (refName.EndsWith("_plan_exec"))
            {
                subId = t?["outputData"]?["subWorkflowId"]?.GetValue<string>();
                break;
            }
        }
        var result = new Dictionary<string, JsonNode?>();
        if (subId is null) return result;
        var sub = await _fixture.FetchWorkflowAsync(subId);
        foreach (var t in sub?["tasks"]?.AsArray() ?? new JsonArray())
        {
            var name = t?["taskDefName"]?.GetValue<string>() ?? "";
            // Tool names are auto-snake_cased by the SDK from method names.
            if (name.StartsWith("s16_"))
            {
                result[name] = t?["outputData"];
            }
        }
        return result;
    }

    // ── 16.1  Ref pipes the whole output across steps ───────────────────

    [SkippableFact]
    public async Task RefPipesWholeOutputAcrossSteps()
    {
        _fixture.RequireServer();

        var harness = BuildRefsHarness();
        var plan = new Plan
        {
            Steps =
            {
                new Step("a")
                {
                    Operations = { new Op("s16_produce", new() { ["record_id"] = "r-001" }) },
                },
                new Step("b")
                {
                    DependsOn = { "a" },
                    Operations = { new Op("s16_enrich", new() { ["record"] = new Ref("a") }) },
                },
            },
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(300));
        var result = await runtime.RunAsync(harness, "go", plan: plan, ct: cts.Token);

        Assert.True(
            result.IsSuccess,
            $"workflow did not COMPLETE: status={result.Status} error={result.Error}");

        var outputs = await FetchStepOutputsAsync(result.ExecutionId);

        // Step A — seed dict.
        var produce = outputs["s16_produce"]!.AsObject();
        Assert.Equal("r-001", produce["record_id"]!.GetValue<string>());
        Assert.Equal(42, produce["value"]!.GetValue<int>());

        // Step B — proves Ref("a") delivered the whole upstream dict.
        // Counterfactual: if Ref were unwired, enrich would receive the
        // literal {"$ref":"a"} marker and value_squared would be 0.
        var enrich = outputs["s16_enrich"]!.AsObject();
        Assert.Equal(
            1764, enrich["value_squared"]!.GetValue<int>());
        Assert.Equal(42, enrich["value"]!.GetValue<int>());
        Assert.Equal("r-001", enrich["record_id"]!.GetValue<string>());
    }

    // ── 16.2  Two Refs in the same args resolve independently ───────────

    [SkippableFact]
    public async Task TwoRefsInSameArgsResolveIndependently()
    {
        _fixture.RequireServer();

        var harness = BuildRefsHarness();
        var plan = new Plan
        {
            Steps =
            {
                new Step("a")
                {
                    Operations = { new Op("s16_produce", new() { ["record_id"] = "r-001" }) },
                },
                new Step("b")
                {
                    DependsOn = { "a" },
                    Operations = { new Op("s16_enrich", new() { ["record"] = new Ref("a") }) },
                },
                new Step("c")
                {
                    DependsOn = { "a", "b" },
                    Operations =
                    {
                        new Op("s16_report", new()
                        {
                            ["record"] = new Ref("a"),
                            ["enriched"] = new Ref("b"),
                        }),
                    },
                },
            },
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(300));
        var result = await runtime.RunAsync(harness, "go", plan: plan, ct: cts.Token);

        Assert.True(result.IsSuccess, $"status={result.Status} error={result.Error}");

        var outputs = await FetchStepOutputsAsync(result.ExecutionId);
        var report = outputs["s16_report"]!.AsObject();

        // Counterfactual: if both Refs collapsed to the same upstream,
        // squared would equal original_value (both 42). Asserting 1764 ≠
        // 42 rules that out.
        Assert.Equal("r-001", report["id"]!.GetValue<string>());
        Assert.Equal(42, report["original_value"]!.GetValue<int>());
        Assert.Equal(1764, report["squared"]!.GetValue<int>());
        Assert.Equal("alpha, beta", report["tags_joined"]!.GetValue<string>());
    }
}
