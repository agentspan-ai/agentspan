// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// 108 — Plan-Execute with cross-step output piping via `Ref`.
//
// The `new Ref("step_id")` helper wires the whole output of an upstream
// step into a downstream step's args. No JSON path, no field selection,
// no internal task-ref naming to memorise — one expression and the
// runtime substitutes the value at execution time.
//
// This example runs a three-step pipeline:
//
//     produce → enrich → report
//
// `produce` emits a record dict, `enrich` adds a derived field via
// Ref("produce"), and `report` reads Ref("enrich") to format a final
// summary. The plan is fully deterministic — no planner LLM required —
// because we pass it directly to RunAsync.

using System.Text.Json;
using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;
using Agentspan.Plans;

// ── Tool implementations ─────────────────────────────────

internal sealed class PipelineTools
{
    [Tool("Return a fixed payload.")]
    public Dictionary<string, object> Produce(string record_id) => new()
    {
        ["record_id"] = record_id,
        ["value"] = 42,
        ["tags"] = new[] { "alpha", "beta" },
    };

    [Tool("Append a derived field. Reads the whole `produce` output via Ref.")]
    public Dictionary<string, object?> Enrich(JsonElement record)
    {
        var dict = JsonSerializer.Deserialize<Dictionary<string, object?>>(record.GetRawText())!;
        var value = ((JsonElement)dict["value"]!).GetInt32();
        dict["value_squared"] = value * value;
        return dict;
    }

    [Tool("Format the final report. Reads BOTH upstream steps via Refs.")]
    public Dictionary<string, object?> Report(JsonElement record, JsonElement enriched)
    {
        var recordId = record.GetProperty("record_id").GetString();
        var value = record.GetProperty("value").GetInt32();
        var tags = record.GetProperty("tags").EnumerateArray()
            .Select(e => e.GetString()!).ToList();
        var squared = enriched.GetProperty("value_squared").GetInt32();
        return new Dictionary<string, object?>
        {
            ["id"] = recordId,
            ["original_value"] = value,
            ["squared"] = squared,
            ["tags_joined"] = string.Join(", ", tags),
            ["summary"] = $"record={recordId} value={value} squared={squared} tags=[{string.Join(", ", tags)}]",
        };
    }
}

// ── Main ─────────────────────────────────────────────────

var planner = new Agent("ref_demo_planner")
{
    Model = Settings.LlmModel,
    Instructions = "(planner unused; static plan supplied)",
};

var harness = new Agent("ref_demo")
{
    Model = Settings.LlmModel,
    Strategy = Strategy.PlanExecute,
    Planner = planner,
    Tools = ToolRegistry.FromInstance(new PipelineTools()),
};

// Typed plan — no JSON strings, no field selectors. Each Ref serialises
// to {"$ref":"<step_id>"} which the server rewrites to the right
// Conductor template at compile time.
var plan = new Plan
{
    Steps =
    {
        new Step("produce")
        {
            Operations =
            {
                new Op("produce", new Dictionary<string, object?> { ["record_id"] = "r-001" }),
            },
        },
        new Step("enrich")
        {
            DependsOn = { "produce" },
            Operations =
            {
                new Op("enrich", new Dictionary<string, object?> { ["record"] = new Ref("produce") }),
            },
        },
        new Step("report")
        {
            DependsOn = { "produce", "enrich" },
            Operations =
            {
                new Op("report", new Dictionary<string, object?>
                {
                    ["record"]   = new Ref("produce"),
                    ["enriched"] = new Ref("enrich"),
                }),
            },
        },
    },
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(harness, "demo", plan: plan);

Console.WriteLine($"status={result.Status} executionId={result.ExecutionId}");
await ShowPipelineOutputsAsync(result.ExecutionId);

// ── Trace helper — reads task outputs from the workflow API ───

static async Task ShowPipelineOutputsAsync(string executionId)
{
    var baseUrl = (Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL")
        ?? "http://localhost:6767/api").Replace("/api", "");
    using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };

    var parentBody = await http.GetStringAsync($"{baseUrl}/api/workflow/{executionId}?includeTasks=true");
    var parent = JsonNode.Parse(parentBody)!.AsObject();
    string? subId = null;
    foreach (var t in parent["tasks"]?.AsArray() ?? new JsonArray())
    {
        var refName = t?["referenceTaskName"]?.GetValue<string>() ?? "";
        if (refName.EndsWith("_plan_exec"))
        {
            subId = t?["outputData"]?["subWorkflowId"]?.GetValue<string>();
            break;
        }
    }
    if (subId is null) return;

    var subBody = await http.GetStringAsync($"{baseUrl}/api/workflow/{subId}?includeTasks=true");
    var sub = JsonNode.Parse(subBody)!.AsObject();

    Console.WriteLine("\n── pipeline trace (Ref data flow) ────────────────────────");
    foreach (var t in sub["tasks"]?.AsArray() ?? new JsonArray())
    {
        var name = t?["taskDefName"]?.GetValue<string>() ?? "";
        if (name is "produce" or "enrich" or "report")
        {
            Console.WriteLine($"\n{name}:");
            Console.WriteLine(t?["outputData"]?.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }
    }
}
