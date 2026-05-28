// Copyright (c) 2026 Agentspan
// Licensed under the MIT License.

using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using System.Web;

namespace Agentspan.Scheduling;

/// <summary>
/// Lifecycle API for cron-based agent schedules. Obtained via <c>runtime.Schedules</c>.
///
/// <para>
/// Operations are keyed by the <strong>wire name</strong> (prefixed with
/// <c>{agent}-</c>) returned by <see cref="ListAsync"/>. Use <see cref="Schedule"/>
/// to construct the user-facing short name; the SDK prefixes it at deploy time.
/// </para>
/// </summary>
public sealed class Schedules
{
    private readonly HttpClient _client;
    private readonly string _baseUrl;

    public Schedules(HttpClient client, string baseUrl)
    {
        _client = client;
        _baseUrl = baseUrl.TrimEnd('/');
    }

    // ── CRUD ───────────────────────────────────────────────────────────

    public async Task SaveAsync(Schedule schedule, string agentName, CancellationToken ct = default)
    {
        schedule.Validate();
        var body = ToSaveRequest(schedule, agentName);
        await RequestAsync(HttpMethod.Post, "/scheduler/schedules", body, ct);
    }

    public async Task<ScheduleInfo> GetAsync(string wireName, CancellationToken ct = default)
    {
        var node = await RequestAsync(HttpMethod.Get,
            $"/scheduler/schedules/{Uri.EscapeDataString(wireName)}", null, ct);
        if (node is not JsonObject obj || obj["name"] is null)
            throw new ScheduleNotFound($"Schedule '{wireName}' not found");
        return FromWorkflowSchedule(obj, null);
    }

    public async Task<IReadOnlyList<ScheduleInfo>> ListAsync(string agentName, CancellationToken ct = default)
    {
        var node = await RequestAsync(HttpMethod.Get,
            $"/scheduler/schedules?workflowName={Uri.EscapeDataString(agentName)}", null, ct);
        if (node is not JsonArray arr) return new List<ScheduleInfo>();
        return arr.OfType<JsonObject>()
            .Select(o => FromWorkflowSchedule(o, agentName))
            .ToList();
    }

    public async Task PauseAsync(string wireName, string? reason = null, CancellationToken ct = default)
    {
        var path = $"/scheduler/schedules/{Uri.EscapeDataString(wireName)}/pause";
        if (reason is not null) path += $"?reason={Uri.EscapeDataString(reason)}";
        await RequestAsync(HttpMethod.Put, path, null, ct);
    }

    public async Task ResumeAsync(string wireName, CancellationToken ct = default)
    {
        await RequestAsync(HttpMethod.Put,
            $"/scheduler/schedules/{Uri.EscapeDataString(wireName)}/resume", null, ct);
    }

    public async Task DeleteAsync(string wireName, CancellationToken ct = default)
    {
        await RequestAsync(HttpMethod.Delete,
            $"/scheduler/schedules/{Uri.EscapeDataString(wireName)}", null, ct);
    }

    public async Task<string> RunNowAsync(ScheduleInfo info, CancellationToken ct = default)
    {
        var body = new JsonObject();
        foreach (var kv in info.Input) body[kv.Key] = JsonValue.Create(kv.Value);
        var node = await RequestAsync(HttpMethod.Post,
            $"/workflow/{Uri.EscapeDataString(info.Agent)}", body, ct);
        if (node is JsonObject obj) return obj["workflowId"]?.GetValue<string>() ?? "";
        return node?.ToString().Trim('"') ?? "";
    }

    public async Task<IReadOnlyList<long>> PreviewNextAsync(
        string cron, int n = 5, long? startAt = null, long? endAt = null, CancellationToken ct = default)
    {
        var qs = new StringBuilder();
        qs.Append("?cronExpression=").Append(Uri.EscapeDataString(cron));
        qs.Append("&limit=").Append(n);
        if (startAt.HasValue) qs.Append("&scheduleStartTime=").Append(startAt.Value);
        if (endAt.HasValue)   qs.Append("&scheduleEndTime=").Append(endAt.Value);
        var node = await RequestAsync(HttpMethod.Get, $"/scheduler/nextFewSchedules{qs}", null, ct);
        if (node is not JsonArray arr) return new List<long>();
        return arr.Select(x => x?.GetValue<long>() ?? 0).ToList();
    }

    // ── Declarative reconcile ─────────────────────────────────────────

    /// <summary>
    /// Tri-state semantics:
    /// <list type="bullet">
    /// <item><c>null</c> → no-op</item>
    /// <item>empty list → purge all schedules whose workflow == agent</item>
    /// <item>non-empty list → upsert listed, prune the rest (scoped to this agent)</item>
    /// </list>
    /// </summary>
    public async Task ReconcileAsync(string agentName, IEnumerable<Schedule>? desired, CancellationToken ct = default)
    {
        if (desired is null) return;
        var desiredList = desired.ToList();
        CheckUniqueNames(desiredList);

        var existing = await ListAsync(agentName, ct);
        var existingWireByShort = existing.ToDictionary(i => i.ShortName, i => i.Name);
        var desiredShort = desiredList.Select(s => s.Name).ToHashSet();

        foreach (var (shortName, wire) in existingWireByShort)
            if (!desiredShort.Contains(shortName))
                await DeleteAsync(wire, ct);
        foreach (var s in desiredList)
            await SaveAsync(s, agentName, ct);
    }

    // ── Internals (also referenced by tests) ──────────────────────────

    public static string Prefix(string agentName, string shortName) => $"{agentName}-{shortName}";

    public static string Unprefix(string agentName, string wireName)
    {
        var p = $"{agentName}-";
        return wireName.StartsWith(p) ? wireName[p.Length..] : wireName;
    }

    public static void CheckUniqueNames(IEnumerable<Schedule> schedules)
    {
        var seen = new HashSet<string>();
        foreach (var s in schedules)
        {
            if (!seen.Add(s.Name))
                throw new ScheduleNameConflict(
                    $"Duplicate schedule name '{s.Name}' — names must be unique per agent");
        }
    }

    public static JsonObject ToSaveRequest(Schedule s, string agentName)
    {
        var swrInput = new JsonObject();
        foreach (var kv in s.Input) swrInput[kv.Key] = JsonValue.Create(kv.Value);

        var swr = new JsonObject { ["name"] = agentName, ["input"] = swrInput };

        var req = new JsonObject
        {
            ["name"] = Prefix(agentName, s.Name),
            ["cronExpression"] = s.Cron,
            ["zoneId"] = s.Timezone,
            ["runCatchupScheduleInstances"] = s.Catchup,
            ["paused"] = s.Paused,
            ["startWorkflowRequest"] = swr,
        };
        if (s.StartAt.HasValue) req["scheduleStartTime"] = s.StartAt.Value;
        if (s.EndAt.HasValue) req["scheduleEndTime"] = s.EndAt.Value;
        if (s.Description is not null) req["description"] = s.Description;
        return req;
    }

    public static ScheduleInfo FromWorkflowSchedule(JsonObject ws, string? agentHint)
    {
        var swr = ws["startWorkflowRequest"] as JsonObject ?? new JsonObject();
        var wireName = ws["name"]?.GetValue<string>() ?? "";
        var swrName = swr["name"]?.GetValue<string>() ?? "";
        var agent = agentHint ?? (string.IsNullOrEmpty(swrName) ? "" : swrName);

        var inputDict = new Dictionary<string, object?>();
        if (swr["input"] is JsonObject inObj)
            foreach (var kv in inObj)
                inputDict[kv.Key] = kv.Value?.GetValue<object>();

        return new ScheduleInfo(
            Name: wireName,
            ShortName: Unprefix(agent, wireName),
            Agent: swrName,
            Cron: ws["cronExpression"]?.GetValue<string>() ?? "",
            Timezone: ws["zoneId"]?.GetValue<string>() ?? "UTC",
            Input: inputDict,
            Paused: ws["paused"]?.GetValue<bool>() ?? false,
            PausedReason: ws["pausedReason"]?.GetValue<string>(),
            Catchup: ws["runCatchupScheduleInstances"]?.GetValue<bool>() ?? false,
            StartAt: ws["scheduleStartTime"]?.GetValue<long>(),
            EndAt: ws["scheduleEndTime"]?.GetValue<long>(),
            Description: ws["description"]?.GetValue<string>(),
            NextRun: ws["nextRunTime"]?.GetValue<long>(),
            CreateTime: ws["createTime"]?.GetValue<long>(),
            UpdateTime: ws["updatedTime"]?.GetValue<long>(),
            CreatedBy: ws["createdBy"]?.GetValue<string>(),
            UpdatedBy: ws["updatedBy"]?.GetValue<string>());
    }

    private async Task<JsonNode?> RequestAsync(HttpMethod method, string path, JsonNode? body, CancellationToken ct)
    {
        var url = $"{_baseUrl}{path}";
        using var req = new HttpRequestMessage(method, url);
        if (body is not null)
            req.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");

        using var resp = await _client.SendAsync(req, ct);
        var text = await resp.Content.ReadAsStringAsync(ct);

        if (!resp.IsSuccessStatusCode)
        {
            if (resp.StatusCode == HttpStatusCode.NotFound)
                throw new ScheduleNotFound(text);
            if (resp.StatusCode == HttpStatusCode.BadRequest && text.ToLower().Contains("cron"))
                throw new InvalidCronExpression(text);
            throw new ScheduleException($"HTTP {(int)resp.StatusCode}: {text}");
        }

        if (string.IsNullOrWhiteSpace(text)) return null;
        var trimmed = text.Trim();
        if (trimmed.StartsWith("{") || trimmed.StartsWith("["))
            return JsonNode.Parse(trimmed);
        return JsonValue.Create(trimmed.Trim('"'));
    }
}
