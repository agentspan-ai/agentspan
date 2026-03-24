using System.Text.Json;

namespace Agentspan;

public enum EventType { Thinking, ToolCall, ToolResult, Handoff, Waiting, Message, Error, Done }
public enum AgentStatus { Completed, Failed, Terminated, TimedOut, Running }

public sealed class AgentResult
{
    public object? Output { get; }
    public string WorkflowId { get; }
    public AgentStatus Status { get; }
    public IReadOnlyList<Dictionary<string, object?>> ToolCalls { get; }
    public bool IsSuccess => Status == AgentStatus.Completed;

    public AgentResult(object? output, string workflowId, AgentStatus status, IReadOnlyList<Dictionary<string, object?>>? toolCalls = null)
    {
        Output = output;
        WorkflowId = workflowId;
        Status = status;
        ToolCalls = toolCalls ?? Array.Empty<Dictionary<string, object?>>().ToList().AsReadOnly();
    }

    public T? GetOutput<T>() where T : class
    {
        if (Output is T t) return t;
        if (Output is string s)
            return JsonSerializer.Deserialize<T>(s);
        if (Output != null)
        {
            var json = JsonSerializer.Serialize(Output);
            return JsonSerializer.Deserialize<T>(json);
        }
        return null;
    }

    public void PrintResult()
    {
        Console.WriteLine($"Status: {Status}");
        Console.WriteLine($"WorkflowId: {WorkflowId}");
        if (Output != null)
            Console.WriteLine($"Output: {(Output is string s ? s : JsonSerializer.Serialize(Output))}");
        if (ToolCalls.Count > 0)
            Console.WriteLine($"Tool calls: {ToolCalls.Count}");
    }
}

public sealed class AgentHandle
{
    private readonly AgentHttpClient _client;
    private readonly AgentConfig _config;
    public string WorkflowId { get; }

    internal AgentHandle(string workflowId, AgentHttpClient client, AgentConfig config)
    {
        WorkflowId = workflowId;
        _client = client;
        _config = config;
    }

    public async Task<AgentResult> WaitAsync(CancellationToken ct = default)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await _client.GetStatusAsync(WorkflowId, ct);
            var wfStatus = status.GetValueOrDefault("status")?.ToString() ?? "";

            if (wfStatus == "COMPLETED")
            {
                var output = status.GetValueOrDefault("output");
                var toolCalls = ParseToolCalls(status.GetValueOrDefault("toolCalls"));
                return new AgentResult(output, WorkflowId, AgentStatus.Completed, toolCalls);
            }
            if (wfStatus == "FAILED" || wfStatus == "TERMINATED" || wfStatus == "TIMED_OUT")
            {
                var agentStatus = wfStatus switch
                {
                    "FAILED" => AgentStatus.Failed,
                    "TERMINATED" => AgentStatus.Terminated,
                    _ => AgentStatus.TimedOut
                };
                return new AgentResult(null, WorkflowId, agentStatus);
            }

            await Task.Delay(_config.StatusPollIntervalMs, ct);
        }
        return new AgentResult(null, WorkflowId, AgentStatus.Failed);
    }

    public async IAsyncEnumerable<AgentEvent> StreamAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        await foreach (var ev in _client.StreamSseAsync(WorkflowId, ct))
            yield return ev;
    }

    public Task ApproveAsync(CancellationToken ct = default) =>
        _client.RespondAsync(WorkflowId, new Dictionary<string, object> { ["approved"] = true }, ct);

    public Task RejectAsync(string reason = "", CancellationToken ct = default) =>
        _client.RespondAsync(WorkflowId, new Dictionary<string, object> { ["approved"] = false, ["reason"] = reason }, ct);

    private static IReadOnlyList<Dictionary<string, object?>> ParseToolCalls(object? raw)
    {
        if (raw is JsonElement je && je.ValueKind == JsonValueKind.Array)
        {
            return je.EnumerateArray()
                .Select(e => e.Deserialize<Dictionary<string, object?>>() ?? new())
                .ToList().AsReadOnly();
        }
        return Array.Empty<Dictionary<string, object?>>().ToList().AsReadOnly();
    }
}

public sealed class AgentEvent
{
    public EventType Type { get; init; }
    public string? Content { get; init; }
    public string? ToolName { get; init; }
    public Dictionary<string, object?>? Args { get; init; }
    public object? Result { get; init; }
    public object? Output { get; init; }
    public string WorkflowId { get; init; } = "";

    public static AgentEvent FromDict(Dictionary<string, object?> d, string workflowId)
    {
        var typeStr = d.GetValueOrDefault("type")?.ToString() ?? "";
        var type = typeStr switch
        {
            "thinking" => EventType.Thinking,
            "tool_call" => EventType.ToolCall,
            "tool_result" => EventType.ToolResult,
            "handoff" => EventType.Handoff,
            "waiting" => EventType.Waiting,
            "message" => EventType.Message,
            "error" => EventType.Error,
            "done" => EventType.Done,
            _ => EventType.Message
        };

        Dictionary<string, object?>? args = null;
        if (d.GetValueOrDefault("args") is JsonElement je && je.ValueKind == JsonValueKind.Object)
            args = je.Deserialize<Dictionary<string, object?>>();

        return new AgentEvent
        {
            Type = type,
            Content = d.GetValueOrDefault("content")?.ToString(),
            ToolName = d.GetValueOrDefault("toolName")?.ToString(),
            Args = args,
            Result = d.GetValueOrDefault("result"),
            Output = d.GetValueOrDefault("output"),
            WorkflowId = workflowId
        };
    }
}
