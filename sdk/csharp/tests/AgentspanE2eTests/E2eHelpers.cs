// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Shared helpers for extracting and navigating plan() agentDef JSON.
// These mirror the Python e2e helper functions:
//   _agent_def(), _tool_names(), _guardrail_by_name(), _all_tasks_flat(), etc.

using System.Text.Json.Nodes;
using Xunit;

namespace Agentspan.E2eTests;

internal static class E2eHelpers
{
    // ── Plan navigation ──────────────────────────────────────────────────

    /// <summary>
    /// Extract plan["workflowDef"]["metadata"]["agentDef"].
    /// Fails with a clear message if the path is missing.
    /// </summary>
    public static JsonNode GetAgentDef(JsonNode? plan)
    {
        var wf = plan?["workflowDef"]
            ?? throw new Exception(
                $"plan() result missing 'workflowDef'. Keys: {Keys(plan)}");

        var meta = wf["metadata"]
            ?? throw new Exception(
                $"workflowDef missing 'metadata'. Keys: {Keys(wf)}");

        return meta["agentDef"]
            ?? throw new Exception(
                $"workflowDef.metadata missing 'agentDef'. Keys: {Keys(meta)}");
    }

    /// <summary>Recursively collect every task from a workflowDef, including nested ones.</summary>
    public static List<JsonNode> AllTasksFlat(JsonNode? workflowDef)
    {
        var result = new List<JsonNode>();
        var top = workflowDef?["tasks"]?.AsArray() ?? [];
        foreach (var t in top)
            if (t is not null) RecurseTask(t, result);
        return result;
    }

    private static void RecurseTask(JsonNode t, List<JsonNode> acc)
    {
        acc.Add(t);
        foreach (var nested in t["loopOver"]?.AsArray() ?? [])
            if (nested is not null) RecurseTask(nested, acc);
        foreach (var (_, caseList) in t["decisionCases"]?.AsObject() ?? new JsonObject())
            foreach (var ct in caseList?.AsArray() ?? [])
                if (ct is not null) RecurseTask(ct, acc);
        foreach (var ct in t["defaultCase"]?.AsArray() ?? [])
            if (ct is not null) RecurseTask(ct, acc);
        foreach (var forkList in t["forkTasks"]?.AsArray() ?? [])
            foreach (var ft in forkList?.AsArray() ?? [])
                if (ft is not null) RecurseTask(ft, acc);
    }

    // ── Tool helpers ─────────────────────────────────────────────────────

    /// <summary>Return all tool names from agentDef.tools.</summary>
    public static List<string> ToolNames(JsonNode agentDef)
        => agentDef["tools"]?.AsArray()
              .Select(t => t?["name"]?.GetValue<string>() ?? "")
              .ToList()
           ?? [];

    /// <summary>Find a tool by name. Fails with a clear message if not found.</summary>
    public static JsonNode GetTool(JsonNode agentDef, string name)
    {
        var tool = agentDef["tools"]?.AsArray()
            .FirstOrDefault(t => t?["name"]?.GetValue<string>() == name);

        if (tool is null)
        {
            var names = ToolNames(agentDef);
            Assert.Fail(
                $"Tool '{name}' not found in agentDef.tools. " +
                $"Available tools: [{string.Join(", ", names)}].");
        }
        return tool!;
    }

    /// <summary>Get the toolType string for a named tool. Fails if tool not found.</summary>
    public static string GetToolType(JsonNode agentDef, string name)
        => GetTool(agentDef, name)["toolType"]?.GetValue<string>()
           ?? throw new Exception($"Tool '{name}' has no toolType field.");

    /// <summary>Get the credentials array for a named tool (null if not present).</summary>
    public static List<string>? GetToolCredentials(JsonNode agentDef, string name)
    {
        var tool = GetTool(agentDef, name);
        var creds = tool["credentials"]?.AsArray();
        if (creds is null) return null;
        return creds.Select(c => c?.GetValue<string>() ?? "").ToList();
    }

    // ── Guardrail helpers ─────────────────────────────────────────────────

    /// <summary>Return all guardrail names from agentDef.guardrails.</summary>
    public static List<string> GuardrailNames(JsonNode agentDef)
        => agentDef["guardrails"]?.AsArray()
              .Select(g => g?["name"]?.GetValue<string>() ?? "")
              .ToList()
           ?? [];

    /// <summary>Find a guardrail by name. Fails with a clear message if not found.</summary>
    public static JsonNode GetGuardrail(JsonNode agentDef, string name)
    {
        var g = agentDef["guardrails"]?.AsArray()
            .FirstOrDefault(g => g?["name"]?.GetValue<string>() == name);

        if (g is null)
        {
            var names = GuardrailNames(agentDef);
            Assert.Fail(
                $"Guardrail '{name}' not found in agentDef.guardrails. " +
                $"Available: [{string.Join(", ", names)}].");
        }
        return g!;
    }

    // ── Sub-agent helpers ─────────────────────────────────────────────────

    /// <summary>Return sub-agent names from agentDef.agents.</summary>
    public static List<string> SubAgentNames(JsonNode agentDef)
        => agentDef["agents"]?.AsArray()
              .Select(a => a?["name"]?.GetValue<string>() ?? "")
              .ToList()
           ?? [];

    // ── Private ───────────────────────────────────────────────────────────

    private static string Keys(JsonNode? node)
        => node is JsonObject obj
            ? string.Join(", ", obj.Select(kv => kv.Key))
            : "(null)";
}
