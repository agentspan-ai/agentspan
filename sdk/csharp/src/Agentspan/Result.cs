// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Agentspan;

// ── Enums ──────────────────────────────────────────────────

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum EventType
{
    [JsonPropertyName("thinking")]        Thinking,
    [JsonPropertyName("tool_call")]       ToolCall,
    [JsonPropertyName("tool_result")]     ToolResult,
    [JsonPropertyName("guardrail_pass")]  GuardrailPass,
    [JsonPropertyName("guardrail_fail")]  GuardrailFail,
    [JsonPropertyName("waiting")]         Waiting,
    [JsonPropertyName("handoff")]         Handoff,
    [JsonPropertyName("message")]         Message,
    [JsonPropertyName("error")]           Error,
    [JsonPropertyName("done")]            Done,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Status
{
    [JsonPropertyName("completed")]   Completed,
    [JsonPropertyName("failed")]      Failed,
    [JsonPropertyName("terminated")]  Terminated,
    [JsonPropertyName("timed_out")]   TimedOut,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum FinishReason
{
    [JsonPropertyName("stop")]       Stop,
    [JsonPropertyName("length")]     Length,
    [JsonPropertyName("tool_calls")] ToolCalls,
    [JsonPropertyName("error")]      Error,
    [JsonPropertyName("cancelled")]  Cancelled,
    [JsonPropertyName("timeout")]    Timeout,
    [JsonPropertyName("guardrail")]  Guardrail,
    [JsonPropertyName("rejected")]   Rejected,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum OnFail
{
    [JsonPropertyName("retry")] Retry,
    [JsonPropertyName("raise")] Raise,
    [JsonPropertyName("fix")]   Fix,
    [JsonPropertyName("human")] Human,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Position
{
    [JsonPropertyName("input")]  Input,
    [JsonPropertyName("output")] Output,
}

// ── Value records ──────────────────────────────────────────

public record TokenUsage(
    [property: JsonPropertyName("promptTokens")]     int PromptTokens,
    [property: JsonPropertyName("completionTokens")] int CompletionTokens,
    [property: JsonPropertyName("totalTokens")]      int TotalTokens
);

public record DeploymentInfo(
    [property: JsonPropertyName("registeredName")] string RegisteredName,
    [property: JsonPropertyName("agentName")]      string AgentName
);

public record CredentialFile(
    string EnvVar,
    string? RelativePath = null,
    string? Content = null
);

public record CodeExecutionConfig(
    bool Enabled = true,
    List<string>? AllowedLanguages = null,
    List<string>? AllowedCommands = null,
    int Timeout = 30
);

public record CliConfig(
    bool Enabled = true,
    List<string>? AllowedCommands = null,
    int Timeout = 30,
    bool AllowShell = false
);

public record ExecutionResult(
    string Output,
    string? Error = null,
    int ExitCode = 0,
    bool TimedOut = false
)
{
    [JsonIgnore] public bool Success => ExitCode == 0 && !TimedOut;
}

public record GuardrailResult(
    bool Passed,
    string? Message = null,
    string? FixedOutput = null
);

// ── AgentEvent ─────────────────────────────────────────────

public record AgentEvent
{
    [JsonPropertyName("type")]          public EventType Type          { get; init; }
    [JsonPropertyName("content")]       public string?   Content       { get; init; }
    [JsonPropertyName("toolName")]      public string?   ToolName      { get; init; }
    [JsonPropertyName("args")]          public Dictionary<string, object>? Args { get; init; }
    [JsonPropertyName("result")]        public object?   Result        { get; init; }
    [JsonPropertyName("target")]        public string?   Target        { get; init; }
    [JsonPropertyName("output")]        public object?   Output        { get; init; }
    [JsonPropertyName("executionId")]   public string?   ExecutionId   { get; init; }
    [JsonPropertyName("guardrailName")] public string?   GuardrailName { get; init; }
    [JsonPropertyName("timestamp")]     public long?     Timestamp     { get; init; }
    [JsonPropertyName("status")]        public string?   Status        { get; init; }
}

// ── AgentResult ────────────────────────────────────────────

public record AgentResult
{
    [JsonPropertyName("executionId")]   public string ExecutionId  { get; init; } = "";
    [JsonPropertyName("correlationId")] public string? CorrelationId { get; init; }
    [JsonPropertyName("output")]        public Dictionary<string, object>? Output { get; init; }
    [JsonPropertyName("messages")]      public List<Dictionary<string, object>>? Messages { get; init; }
    [JsonPropertyName("toolCalls")]     public List<Dictionary<string, object>>? ToolCalls { get; init; }
    [JsonPropertyName("status")]        public Status Status       { get; init; }
    [JsonPropertyName("finishReason")]  public FinishReason? FinishReason { get; init; }
    [JsonPropertyName("error")]         public string? Error       { get; init; }
    [JsonPropertyName("tokenUsage")]    public TokenUsage? TokenUsage { get; init; }
    [JsonPropertyName("metadata")]      public Dictionary<string, object>? Metadata { get; init; }
    [JsonPropertyName("events")]        public List<AgentEvent>? Events { get; init; }
    [JsonPropertyName("subResults")]    public Dictionary<string, object>? SubResults { get; init; }

    // Convenience properties
    [JsonIgnore] public bool IsSuccess  => Status == Status.Completed;
    [JsonIgnore] public bool IsFailed   => Status == Status.Failed;
    [JsonIgnore] public bool IsRejected => FinishReason == Agentspan.FinishReason.Rejected;

    /// <summary>Print a one-line summary of the result.</summary>
    public void PrintResult()
    {
        var text = Output?.GetValueOrDefault("result")?.ToString()
                ?? Output?.GetValueOrDefault("output")?.ToString()
                ?? "(no result)";
        Console.WriteLine($"[{Status}] {text}");
    }
}

// ── AgentStatus ────────────────────────────────────────────

public record AgentStatus
{
    [JsonPropertyName("executionId")]  public string ExecutionId  { get; init; } = "";
    [JsonPropertyName("isComplete")]   public bool IsComplete     { get; init; }
    [JsonPropertyName("isRunning")]    public bool IsRunning      { get; init; }
    [JsonPropertyName("isWaiting")]    public bool IsWaiting      { get; init; }
    [JsonPropertyName("output")]       public object? Output      { get; init; }
    [JsonPropertyName("status")]       public string? StatusValue { get; init; }
    [JsonPropertyName("reason")]       public string? Reason      { get; init; }
    [JsonPropertyName("currentTask")]  public string? CurrentTask { get; init; }
    [JsonPropertyName("pendingTool")]  public Dictionary<string, object>? PendingTool { get; init; }
    [JsonPropertyName("tokenUsage")]   public TokenUsage? TokenUsage { get; init; }
}

// ── AgentHandle ────────────────────────────────────────────

public sealed class AgentHandle
{
    private readonly string _executionId;
    private readonly AgentHttpClient _http;

    internal AgentHandle(string executionId, AgentHttpClient http)
    {
        _executionId = executionId;
        _http = http;
    }

    public string ExecutionId => _executionId;

    /// <summary>Poll until the agent completes, then return the result.</summary>
    public async Task<AgentResult> WaitAsync(CancellationToken cancellationToken = default)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            var status = await _http.GetStatusAsync(_executionId, cancellationToken);
            var s = status?["status"]?.GetValue<string>() ?? "";
            if (s is "COMPLETED" or "FAILED" or "TERMINATED" or "TIMED_OUT")
                return BuildResult(status!, s);
            await Task.Delay(500, cancellationToken);
        }
        throw new OperationCanceledException();
    }

    /// <summary>Stream events as they arrive.</summary>
    public IAsyncEnumerable<AgentEvent> StreamAsync(CancellationToken cancellationToken = default)
        => _http.StreamEventsAsync(_executionId, cancellationToken);

    public async Task RespondAsync(object response, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, response, cancellationToken);

    public async Task ApproveAsync(CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, new { approved = true }, cancellationToken);

    public async Task RejectAsync(string? reason = null, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, new { approved = false, reason }, cancellationToken);

    private static AgentResult BuildResult(JsonNode status, string statusStr)
    {
        var output = status["output"];
        var parsedStatus = statusStr switch
        {
            "COMPLETED"  => Status.Completed,
            "FAILED"     => Status.Failed,
            "TERMINATED" => Status.Terminated,
            "TIMED_OUT"  => Status.TimedOut,
            _            => Status.Completed,
        };

        Dictionary<string, object>? outputDict = null;
        if (output is JsonObject obj)
        {
            outputDict = JsonSerializer.Deserialize<Dictionary<string, object>>(
                obj.ToJsonString(), AgentspanJson.Options);
        }
        else if (output is not null)
        {
            outputDict = new Dictionary<string, object> { ["result"] = output.ToString() };
        }

        return new AgentResult
        {
            ExecutionId = status["executionId"]?.GetValue<string>() ?? "",
            Status = parsedStatus,
            Output = outputDict,
            Error = status["error"]?.GetValue<string>(),
        };
    }
}
