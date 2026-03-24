using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Agentspan;

public sealed class AgentHttpClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _serverUrl;
    private static readonly JsonSerializerOptions _jsonOpts = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    public AgentHttpClient(AgentConfig config)
    {
        _serverUrl = config.ServerUrl.TrimEnd('/');
        _http = new HttpClient();
        if (!string.IsNullOrEmpty(config.AuthKey))
            _http.DefaultRequestHeaders.Add("X-Auth-Key", config.AuthKey);
        if (!string.IsNullOrEmpty(config.AuthSecret))
            _http.DefaultRequestHeaders.Add("X-Auth-Secret", config.AuthSecret);
    }

    public async Task<Dictionary<string, object?>> StartAgentAsync(Dictionary<string, object?> payload, CancellationToken ct = default)
    {
        var resp = await PostJsonAsync("/agent/start", payload, ct);
        return await ReadJsonAsync(resp);
    }

    public async Task<Dictionary<string, object?>> GetStatusAsync(string workflowId, CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{_serverUrl}/agent/{workflowId}/status", ct);
        resp.EnsureSuccessStatusCode();
        return await ReadJsonAsync(resp);
    }

    public async Task RespondAsync(string workflowId, Dictionary<string, object> body, CancellationToken ct = default)
    {
        var resp = await PostJsonAsync($"/agent/{workflowId}/respond", body, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async IAsyncEnumerable<AgentEvent> StreamSseAsync(string workflowId, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var url = $"{_serverUrl}/agent/stream/{workflowId}";
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));

        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
            if (!resp.IsSuccessStatusCode)
                yield break;
        }
        catch { yield break; }

        using (resp)
        {
            await using var stream = await resp.Content.ReadAsStreamAsync(ct);
            using var reader = new System.IO.StreamReader(stream);

            string? eventType = null;
            string? eventId = null;
            var dataLines = new List<string>();

            while (!reader.EndOfStream && !ct.IsCancellationRequested)
            {
                var line = await reader.ReadLineAsync(ct);
                if (line == null) break;

                if (line.StartsWith(":")) continue; // heartbeat/comment

                if (line == "")
                {
                    if (dataLines.Count > 0)
                    {
                        var dataStr = string.Join("\n", dataLines);
                        Dictionary<string, object?>? data = null;
                        try { data = JsonSerializer.Deserialize<Dictionary<string, object?>>(dataStr, _jsonOpts); } catch { }
                        if (data != null)
                            yield return AgentEvent.FromDict(data, workflowId);
                    }
                    eventType = null; eventId = null; dataLines.Clear();
                    continue;
                }

                if (line.StartsWith("event:")) eventType = line[6..].Trim();
                else if (line.StartsWith("id:")) eventId = line[3..].Trim();
                else if (line.StartsWith("data:")) dataLines.Add(line[5..].Trim());
            }

            // Process any remaining data (stream ended without trailing blank line)
            if (dataLines.Count > 0)
            {
                var dataStr = string.Join("\n", dataLines);
                Dictionary<string, object?>? data = null;
                try { data = JsonSerializer.Deserialize<Dictionary<string, object?>>(dataStr, _jsonOpts); } catch { }
                if (data != null)
                    yield return AgentEvent.FromDict(data, workflowId);
            }

            // Suppress unused variable warnings
            _ = eventType;
            _ = eventId;
        }
    }

    // Conductor task worker endpoints
    public async Task<Dictionary<string, object?>?> PollTaskAsync(string taskType, CancellationToken ct = default)
    {
        try
        {
            var resp = await _http.GetAsync($"{_serverUrl}/tasks/poll/{taskType}", ct);
            if (resp.StatusCode == System.Net.HttpStatusCode.NoContent || !resp.IsSuccessStatusCode)
                return null;
            var content = await resp.Content.ReadAsStringAsync(ct);
            if (string.IsNullOrWhiteSpace(content) || content == "null") return null;
            return JsonSerializer.Deserialize<Dictionary<string, object?>>(content, _jsonOpts);
        }
        catch { return null; }
    }

    public async Task UpdateTaskAsync(string taskId, string workflowInstanceId, string status, Dictionary<string, object?> outputData, CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?>
        {
            ["workflowInstanceId"] = workflowInstanceId,
            ["taskId"] = taskId,
            ["status"] = status,
            ["outputData"] = outputData,
        };
        await PostJsonAsync("/tasks/" + taskId, body, ct);
    }

    private async Task<HttpResponseMessage> PostJsonAsync(string path, object body, CancellationToken ct)
    {
        var url = path.StartsWith("/") ? _serverUrl + path : path;
        var json = JsonSerializer.Serialize(body, _jsonOpts);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var resp = await _http.PostAsync(url, content, ct);
        resp.EnsureSuccessStatusCode();
        return resp;
    }

    private static async Task<Dictionary<string, object?>> ReadJsonAsync(HttpResponseMessage resp)
    {
        var json = await resp.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<Dictionary<string, object?>>(json, _jsonOpts)
            ?? new Dictionary<string, object?>();
    }

    public void Dispose() => _http.Dispose();
}
