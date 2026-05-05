// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Agentspan;

internal sealed class AgentHttpClient : IDisposable
{
    private readonly HttpClient _client;
    private readonly string _baseUrl;

    public AgentHttpClient(string serverUrl, string? authKey = null, string? authSecret = null)
    {
        _baseUrl = serverUrl.TrimEnd('/');
        _client = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
        if (authKey    is not null) _client.DefaultRequestHeaders.Add("X-Auth-Key", authKey);
        if (authSecret is not null) _client.DefaultRequestHeaders.Add("X-Auth-Secret", authSecret);
    }

    // ── Agent API ───────────────────────────────────────────

    public async Task<string> StartAsync(JsonObject payload, CancellationToken ct = default)
    {
        var json = payload.ToJsonString();
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/agent/start", content, ct);

        if (!resp.IsSuccessStatusCode)
        {
            var body = await resp.Content.ReadAsStringAsync(ct);
            throw new AgentApiException((int)resp.StatusCode, $"{resp.ReasonPhrase}: {body}", body);
        }

        var node = await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
        return node?["executionId"]?.GetValue<string>()
            ?? throw new AgentApiException(200, "No executionId in start response");
    }

    /// <summary>Deploy (register) an agent on the server without starting execution.</summary>
    public async Task<string> DeployAsync(JsonObject agentConfig, CancellationToken ct = default)
    {
        var payload = new JsonObject { ["agentConfig"] = agentConfig };
        var json = payload.ToJsonString();
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/agent/deploy", content, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var body = await resp.Content.ReadAsStringAsync(ct);
            throw new AgentApiException((int)resp.StatusCode, $"{resp.ReasonPhrase}: {body}", body);
        }
        var node = await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
        return node?["agentName"]?.GetValue<string>() ?? "";
    }

    /// <summary>Compile an agent to a Conductor WorkflowDef without executing it.</summary>
    public async Task<JsonNode?> CompileAsync(JsonObject agentConfig, CancellationToken ct = default)
    {
        var payload = new JsonObject { ["agentConfig"] = agentConfig };
        var json = payload.ToJsonString();
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/agent/compile", content, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var body = await resp.Content.ReadAsStringAsync(ct);
            throw new AgentApiException((int)resp.StatusCode, $"{resp.ReasonPhrase}: {body}", body);
        }
        return await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
    }

    public async Task<JsonNode?> GetStatusAsync(string executionId, CancellationToken ct = default)
    {
        using var resp = await _client.GetAsync($"{_baseUrl}/agent/{executionId}/status", ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
    }

    /// <summary>Fetch the full execution record (includes tokenUsage, finishReason).</summary>
    public async Task<JsonNode?> GetExecutionAsync(string executionId, CancellationToken ct = default)
    {
        try
        {
            using var resp = await _client.GetAsync($"{_baseUrl}/agent/execution/{executionId}", ct);
            if (!resp.IsSuccessStatusCode) return null;
            return await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
        }
        catch { return null; }
    }

    public async Task RespondAsync(string executionId, object body, CancellationToken ct = default)
    {
        var json = JsonSerializer.Serialize(body, AgentspanJson.Options);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/agent/{executionId}/respond", content, ct);
        resp.EnsureSuccessStatusCode();
    }

    /// <summary>Push a message into a running agent's Workflow Message Queue.</summary>
    public async Task SendWorkflowMessageAsync(string executionId, object message, CancellationToken ct = default)
    {
        object payload = message is string s
            ? new Dictionary<string, object> { ["message"] = s }
            : message;
        var json = JsonSerializer.Serialize(payload, AgentspanJson.Options);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/workflow/{executionId}/messages", content, ct);
        resp.EnsureSuccessStatusCode();
    }

    /// <summary>Gracefully stop an agent — sets _stop_requested and unblocks WMQ waits.</summary>
    public async Task StopAgentAsync(string executionId, CancellationToken ct = default)
    {
        // Signal the agent to stop
        using var emptyContent = new StringContent("{}", Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/agent/{executionId}/stop", emptyContent, ct);
        // Best-effort — ignore failures (agent may have already completed)

        // Also unblock any blocking PULL_WORKFLOW_MESSAGES wait
        try
        {
            await SendWorkflowMessageAsync(executionId, new Dictionary<string, object> { ["_signal"] = "stop" }, ct);
        }
        catch { /* ignore — WMQ may not be enabled */ }
    }

    /// <summary>Immediately cancel an agent execution (TERMINATED status).</summary>
    public async Task CancelAgentAsync(string executionId, string reason = "", CancellationToken ct = default)
    {
        var url = string.IsNullOrEmpty(reason)
            ? $"{_baseUrl}/workflow/{executionId}"
            : $"{_baseUrl}/workflow/{executionId}?reason={Uri.EscapeDataString(reason)}";
        using var req = new HttpRequestMessage(HttpMethod.Delete, url);
        using var resp = await _client.SendAsync(req, ct);
        // Best-effort
    }

    // ── SSE streaming ───────────────────────────────────────

    public async IAsyncEnumerable<AgentEvent> StreamEventsAsync(
        string executionId,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get,
            $"{_baseUrl}/agent/stream/{executionId}");
        request.Headers.Accept.ParseAdd("text/event-stream");

        using var resp = await _client.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead, ct);
        resp.EnsureSuccessStatusCode();

        await using var stream = await resp.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream);

        string? eventType = null;
        string? eventId   = null;
        var dataLines = new StringBuilder();

        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null) break; // end of stream

            // Heartbeat lines (start with ':') — skip
            if (line.StartsWith(':')) continue;

            if (line.StartsWith("event:"))
            {
                eventType = line["event:".Length..].Trim();
            }
            else if (line.StartsWith("id:"))
            {
                eventId = line["id:".Length..].Trim();
            }
            else if (line.StartsWith("data:"))
            {
                if (dataLines.Length > 0) dataLines.Append('\n');
                dataLines.Append(line["data:".Length..].TrimStart());
            }
            else if (line.Length == 0 && dataLines.Length > 0)
            {
                // Blank line = end of event block
                var ev = ParseEvent(eventType, dataLines.ToString());
                eventType = null;
                eventId   = null;
                dataLines.Clear();

                if (ev is not null)
                {
                    yield return ev;
                    if (ev.Type == EventType.Done) yield break;
                }
            }
        }
    }

    private static AgentEvent? ParseEvent(string? eventType, string data)
    {
        JsonNode? node = null;
        try { node = JsonNode.Parse(data); } catch { /* skip malformed */ }

        return eventType switch
        {
            "thinking" => new AgentEvent
            {
                Type    = EventType.Thinking,
                Content = node?["content"]?.GetValue<string>(),
            },
            "tool_call" => new AgentEvent
            {
                Type     = EventType.ToolCall,
                ToolName = node?["toolName"]?.GetValue<string>(),
            },
            "tool_result" => new AgentEvent
            {
                Type     = EventType.ToolResult,
                ToolName = node?["toolName"]?.GetValue<string>(),
            },
            "guardrail_pass" => new AgentEvent
            {
                Type          = EventType.GuardrailPass,
                GuardrailName = node?["guardrailName"]?.GetValue<string>(),
            },
            "guardrail_fail" => new AgentEvent
            {
                Type          = EventType.GuardrailFail,
                GuardrailName = node?["guardrailName"]?.GetValue<string>(),
                Content       = node?["message"]?.GetValue<string>(),
            },
            "waiting" => new AgentEvent { Type = EventType.Waiting },
            "handoff"  => new AgentEvent
            {
                Type   = EventType.Handoff,
                Target = node?["target"]?.GetValue<string>(),
            },
            "done" => new AgentEvent
            {
                Type    = EventType.Done,
                Status  = node?["output"]?["finishReason"]?.GetValue<string>()
                       ?? node?["status"]?.GetValue<string>(),
                Content = ExtractOutputText(node?["output"]),
            },
            "error" => new AgentEvent
            {
                Type    = EventType.Error,
                Content = node?["message"]?.GetValue<string>(),
            },
            _ => null,
        };
    }

    private static string? ExtractOutputText(JsonNode? output)
    {
        if (output is null) return null;
        if (output is JsonObject obj && obj.TryGetPropertyValue("result", out var r))
            return r?.GetValue<string>();
        if (output is JsonValue v)
        {
            try { return v.GetValue<string>(); } catch { return null; }
        }
        return null;
    }

    // ── Credential resolution ────────────────────────────────

    /// <summary>
    /// Resolve credential values from the server using the execution token.
    /// Returns a dict of name → plaintext value (empty if names is empty or token is null).
    /// </summary>
    public async Task<Dictionary<string, string>> ResolveCredentialsAsync(
        string? executionToken, IEnumerable<string> names, CancellationToken ct = default)
    {
        var nameList = names.ToList();
        if (nameList.Count == 0 || string.IsNullOrEmpty(executionToken))
            return new Dictionary<string, string>();

        try
        {
            var body = JsonSerializer.Serialize(new { token = executionToken, names = nameList },
                AgentspanJson.Options);
            using var content = new StringContent(body, System.Text.Encoding.UTF8, "application/json");
            using var resp = await _client.PostAsync($"{_baseUrl}/credentials/resolve", content, ct);

            if (!resp.IsSuccessStatusCode) return new Dictionary<string, string>();

            var result = await resp.Content.ReadFromJsonAsync<Dictionary<string, string>>(
                cancellationToken: ct);
            return result ?? new Dictionary<string, string>();
        }
        catch { return new Dictionary<string, string>(); }
    }

    // ── Run by name ──────────────────────────────────────────

    /// <summary>Start a pre-deployed workflow by name (no agentConfig payload).</summary>
    public async Task<string> StartWorkflowByNameAsync(
        string workflowName, string prompt, string sessionId = "", CancellationToken ct = default)
    {
        var input = new Dictionary<string, object?>
        {
            ["prompt"]     = prompt,
            ["media"]      = Array.Empty<string>(),
            ["session_id"] = sessionId ?? "",
            ["context"]    = new Dictionary<string, object>(),
        };
        var payload = new Dictionary<string, object?> { ["name"] = workflowName, ["input"] = input };
        var json = JsonSerializer.Serialize(payload);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        using var resp = await _client.PostAsync($"{_baseUrl}/workflow", content, ct);

        if (!resp.IsSuccessStatusCode)
        {
            var body = await resp.Content.ReadAsStringAsync(ct);
            throw new AgentApiException((int)resp.StatusCode, $"{resp.ReasonPhrase}: {body}", body);
        }

        // Returns the execution ID as a bare string
        var executionId = await resp.Content.ReadAsStringAsync(ct);
        return executionId.Trim('"', ' ', '\n', '\r');
    }

    // ── Workflow metadata ────────────────────────────────────

    /// <summary>Fetch the workflow definition (without tasks) to read taskToDomain.</summary>
    public async Task<JsonNode?> GetWorkflowAsync(string executionId, CancellationToken ct = default)
    {
        try
        {
            using var resp = await _client.GetAsync(
                $"{_baseUrl}/workflow/{executionId}?includeTasks=false", ct);
            if (!resp.IsSuccessStatusCode) return null;
            return await resp.Content.ReadFromJsonAsync<JsonNode>(cancellationToken: ct);
        }
        catch { return null; }
    }

    // ── Worker / task polling ────────────────────────────────

    /// <summary>Poll for a single task, returning raw <see cref="JsonElement"/> or null.</summary>
    public async Task<JsonElement?> PollTaskRawAsync(string taskType, string? domain = null, CancellationToken ct = default)
    {
        try
        {
            var url = string.IsNullOrEmpty(domain)
                ? $"{_baseUrl}/tasks/poll/{Uri.EscapeDataString(taskType)}"
                : $"{_baseUrl}/tasks/poll/{Uri.EscapeDataString(taskType)}?workerDomain={Uri.EscapeDataString(domain)}";
            using var resp = await _client.GetAsync(url, ct);

            if (resp.StatusCode is System.Net.HttpStatusCode.NoContent or
                System.Net.HttpStatusCode.NotFound)
                return null;
            if (!resp.IsSuccessStatusCode) return null;

            var text = await resp.Content.ReadAsStringAsync(ct);
            if (string.IsNullOrWhiteSpace(text) || text == "null") return null;

            return JsonSerializer.Deserialize<JsonElement>(text);
        }
        catch (OperationCanceledException) { throw; }
        catch { return null; }
    }

    public async Task ReportTaskSuccessAsync(
        string taskId, string workflowId, object outputData, CancellationToken ct = default)
    {
        var body = JsonSerializer.Serialize(new
        {
            taskId,
            workflowInstanceId = workflowId,
            status = "COMPLETED",
            outputData,
        }, AgentspanJson.Options);

        using var content = new StringContent(body, Encoding.UTF8, "application/json");
        await _client.PostAsync($"{_baseUrl}/tasks", content, ct);
        // Best-effort: ignore errors on task reporting
    }

    public async Task ReportTaskFailureAsync(
        string taskId, string workflowId, string reason,
        bool terminal = true, CancellationToken ct = default)
    {
        var body = JsonSerializer.Serialize(new
        {
            taskId,
            workflowInstanceId = workflowId,
            status = terminal ? "FAILED_WITH_TERMINAL_ERROR" : "FAILED",
            reasonForIncompletion = reason,
        }, AgentspanJson.Options);

        using var content = new StringContent(body, Encoding.UTF8, "application/json");
        await _client.PostAsync($"{_baseUrl}/tasks", content, ct);
    }

    public void Dispose() => _client.Dispose();
}
