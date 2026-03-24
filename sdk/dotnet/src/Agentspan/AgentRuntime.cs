using System.Text.Json;

namespace Agentspan;

public sealed class AgentRuntime : IDisposable, IAsyncDisposable
{
    private readonly AgentConfig _config;
    private readonly AgentHttpClient _httpClient;
    private readonly WorkerManager _workerManager;
    private readonly AgentConfigSerializer _serializer = new();

    public AgentRuntime(AgentConfig? config = null)
    {
        _config = config ?? AgentConfig.FromEnv();
        _httpClient = new AgentHttpClient(_config);
        _workerManager = new WorkerManager(_httpClient, _config);
    }

    // Sync convenience wrappers
    public AgentResult Run(Agent agent, string prompt, string? sessionId = null)
        => RunAsync(agent, prompt, sessionId).GetAwaiter().GetResult();

    public AgentHandle Start(Agent agent, string prompt, string? sessionId = null)
        => StartAsync(agent, prompt, sessionId).GetAwaiter().GetResult();

    public IEnumerable<AgentEvent> Stream(Agent agent, string prompt, string? sessionId = null)
        => StreamAsync(agent, prompt, sessionId).ToBlockingEnumerable();

    // Async methods
    public async Task<AgentResult> RunAsync(Agent agent, string prompt, string? sessionId = null, CancellationToken ct = default)
    {
        PrepareWorkers(agent);
        _workerManager.Start();
        var handle = await StartAsync(agent, prompt, sessionId, ct);
        return await handle.WaitAsync(ct);
    }

    public async Task<AgentHandle> StartAsync(Agent agent, string prompt, string? sessionId = null, CancellationToken ct = default)
    {
        PrepareWorkers(agent);
        _workerManager.Start();

        var agentConfig = _serializer.Serialize(agent);
        var payload = new Dictionary<string, object?>
        {
            ["agentConfig"] = agentConfig,
            ["prompt"] = prompt,
        };
        if (!string.IsNullOrEmpty(sessionId))
            payload["sessionId"] = sessionId;

        var response = await _httpClient.StartAgentAsync(payload, ct);
        var workflowId = response.GetValueOrDefault("workflowId")?.ToString()
            ?? response.GetValueOrDefault("id")?.ToString()
            ?? throw new InvalidOperationException("No workflowId in start response");

        return new AgentHandle(workflowId, _httpClient, _config);
    }

    public async IAsyncEnumerable<AgentEvent> StreamAsync(
        Agent agent,
        string prompt,
        string? sessionId = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var handle = await StartAsync(agent, prompt, sessionId, ct);
        await foreach (var ev in handle.StreamAsync(ct))
            yield return ev;
    }

    private void PrepareWorkers(Agent agent)
    {
        foreach (var tool in agent.Tools)
        {
            if (tool.Func != null && !string.IsNullOrEmpty(tool.Name))
            {
                var capturedTool = tool;
                _workerManager.RegisterWorker(capturedTool.Name, inputData =>
                {
                    // If the Func is already a Func<Dictionary<string,object?>, object?> (from ToolRegistry)
                    if (capturedTool.Func is Func<Dictionary<string, object?>, object?> dictFunc)
                    {
                        var result = dictFunc(inputData);
                        return NormalizeOutput(result);
                    }

                    // Fallback: invoke via DynamicInvoke with resolved arguments
                    var method = capturedTool.Func.Method;
                    var parameters = method.GetParameters()
                        .Where(p => p.ParameterType != typeof(CancellationToken))
                        .ToArray();

                    var args = parameters.Select(p =>
                    {
                        var paramName = p.Name ?? "";
                        if (inputData.TryGetValue(paramName, out var val))
                            return ConvertValue(val, p.ParameterType);
                        return p.ParameterType.IsValueType ? Activator.CreateInstance(p.ParameterType) : null;
                    }).ToArray();

                    var invokeResult = capturedTool.Func.DynamicInvoke(args);
                    return NormalizeOutput(invokeResult);
                });
            }
        }

        // Recurse into sub-agents
        foreach (var sub in agent.SubAgents)
            PrepareWorkers(sub);
        if (agent.Router != null)
            PrepareWorkers(agent.Router);
    }

    private static Dictionary<string, object?> NormalizeOutput(object? result)
    {
        if (result is Dictionary<string, object?> d) return d;
        if (result is Dictionary<string, object> d2) return d2.ToDictionary(k => k.Key, k => (object?)k.Value);
        return new Dictionary<string, object?> { ["result"] = result };
    }

    private static object? ConvertValue(object? val, Type targetType)
    {
        if (val == null) return targetType.IsValueType ? Activator.CreateInstance(targetType) : null;
        if (val is System.Text.Json.JsonElement je)
        {
            return targetType == typeof(string) ? je.GetString() :
                   targetType == typeof(int) ? je.GetInt32() :
                   targetType == typeof(long) ? je.GetInt64() :
                   targetType == typeof(double) ? je.GetDouble() :
                   targetType == typeof(bool) ? je.GetBoolean() :
                   (object?)je.Deserialize(targetType);
        }
        if (targetType == typeof(string)) return val.ToString();
        try { return Convert.ChangeType(val, targetType); } catch { return val; }
    }

    public void Dispose()
    {
        _workerManager.Dispose();
        _httpClient.Dispose();
    }

    public async ValueTask DisposeAsync()
    {
        await _workerManager.DisposeAsync();
        _httpClient.Dispose();
    }
}
