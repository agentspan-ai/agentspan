// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Conductor.AI;

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
    bool AllowShell = false,
    string? WorkingDir = null
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
    [JsonIgnore] public bool IsRejected => FinishReason == Conductor.AI.FinishReason.Rejected;

    /// <summary>Print a formatted summary of the result, mirroring Python's print_result().</summary>
    public void PrintResult()
    {
        const int width = 50;
        var border = new string('═', width);
        Console.WriteLine($"\n╒{border}╕");
        Console.WriteLine($"│ {"Agent Output".PadRight(width - 1)}│");
        Console.WriteLine($"╘{border}╛");
        Console.WriteLine();

        if (IsFailed && Error is not null)
        {
            Console.WriteLine($"ERROR: {Error}");
            Console.WriteLine();
        }
        else if (Output is not null)
        {
            if (Output.TryGetValue("result", out var result) && result is not null)
            {
                Console.WriteLine(result);
                Console.WriteLine();
            }
            else
            {
                foreach (var (key, value) in Output)
                {
                    Console.WriteLine($"--- {key} ---");
                    Console.WriteLine(value);
                    Console.WriteLine();
                }
            }
        }

        if (TokenUsage is not null)
            Console.WriteLine($"Tokens: {TokenUsage.TotalTokens} total ({TokenUsage.PromptTokens} prompt, {TokenUsage.CompletionTokens} completion)");
        else
            Console.WriteLine("Tokens: —");

        if (FinishReason.HasValue)
            Console.WriteLine($"Finish reason: FinishReason.{FinishReason.Value}");

        if (!string.IsNullOrEmpty(ExecutionId))
            Console.WriteLine($"Execution ID: {ExecutionId}");

        Console.WriteLine();
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
    private readonly AgentClient _http;
    private readonly string? _runId;

    internal AgentHandle(string executionId, AgentClient http, string? runId = null)
    {
        _executionId = executionId;
        _http = http;
        _runId = runId;
    }

    public string ExecutionId => _executionId;

    /// <summary>
    /// The domain UUID used for domain-based routing (stateful agents).
    /// Set when the agent was started with <see cref="Agent.Stateful"/> = true,
    /// or when resuming an existing execution via <see cref="AgentRuntime.ResumeAsync"/>.
    /// </summary>
    public string? RunId => _runId;

    /// <summary>Poll until the agent completes, then return the result.</summary>
    public async Task<AgentResult> WaitAsync(CancellationToken cancellationToken = default)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            var status = await _http.GetStatusAsync(_executionId, cancellationToken);
            var s = status?["status"]?.GetValue<string>() ?? "";
            if (s is "COMPLETED" or "FAILED" or "TERMINATED" or "TIMED_OUT")
            {
                // Fetch full execution record for token usage and finish reason
                var execution = await _http.GetExecutionAsync(_executionId, cancellationToken);
                return BuildResult(status!, s, execution);
            }
            await Task.Delay(500, cancellationToken);
        }
        throw new OperationCanceledException();
    }

    /// <summary>Stream events as they arrive.</summary>
    public IAsyncEnumerable<AgentEvent> StreamAsync(CancellationToken cancellationToken = default)
        => _http.StreamEventsAsync(_executionId, cancellationToken);

    /// <summary>Check the current status without blocking.</summary>
    public async Task<AgentStatus> GetStatusAsync(CancellationToken cancellationToken = default)
    {
        var node = await _http.GetStatusAsync(_executionId, cancellationToken);
        if (node is null) return new AgentStatus { ExecutionId = _executionId };

        return new AgentStatus
        {
            ExecutionId  = node["executionId"]?.GetValue<string>() ?? _executionId,
            IsComplete   = node["isComplete"]?.GetValue<bool>() ?? false,
            IsRunning    = node["isRunning"]?.GetValue<bool>() ?? false,
            IsWaiting    = node["isWaiting"]?.GetValue<bool>() ?? false,
            StatusValue  = node["status"]?.GetValue<string>(),
            Reason       = node["reason"]?.GetValue<string>(),
            CurrentTask  = node["currentTask"]?.GetValue<string>(),
        };
    }

    public async Task RespondAsync(object response, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, response, cancellationToken);

    public async Task ApproveAsync(CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, new { approved = true }, cancellationToken);

    /// <summary>Approve the waiting HITL task with a comment reason.</summary>
    public async Task ApproveAsync(string comment, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, new { approved = true, reason = comment }, cancellationToken);

    public async Task RejectAsync(string? reason = null, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(_executionId, new { approved = false, reason }, cancellationToken);

    // ── Event-targeted HITL ──────────────────────────────────
    // Under HANDOFF/SEQUENTIAL/PARALLEL strategies the HUMAN task lives in a
    // sub-execution. Pass the WAITING event so the response targets that event's
    // executionId rather than the root. Mirrors Java's AgentStream.approve(event).

    /// <summary>Approve the HITL task that emitted the given WAITING event (targets its sub-execution).</summary>
    public async Task ApproveAsync(AgentEvent waitingEvent, string? comment = null, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(EventExecId(waitingEvent),
            comment is null ? new { approved = true } : new { approved = true, reason = comment }, cancellationToken);

    /// <summary>Reject the HITL task that emitted the given WAITING event (targets its sub-execution).</summary>
    public async Task RejectAsync(AgentEvent waitingEvent, string reason, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(EventExecId(waitingEvent), new { approved = false, reason }, cancellationToken);

    /// <summary>Send an arbitrary structured response to the execution that emitted the given event.</summary>
    public async Task RespondAsync(AgentEvent waitingEvent, object response, CancellationToken cancellationToken = default)
        => await _http.RespondAsync(EventExecId(waitingEvent), response, cancellationToken);

    private string EventExecId(AgentEvent e) => e.ExecutionId ?? _executionId;

    // ── Waiting helpers ──────────────────────────────────────

    /// <summary>True if the execution is currently paused for human input. Swallows transient errors.</summary>
    public async Task<bool> IsWaitingAsync(CancellationToken cancellationToken = default)
    {
        try { return (await GetStatusAsync(cancellationToken)).IsWaiting; }
        catch { return false; }
    }

    /// <summary>
    /// Poll until the execution pauses for human input (returns true) or reaches a
    /// terminal state (returns false). Returns false on timeout.
    /// </summary>
    public async Task<bool> WaitUntilWaitingAsync(
        TimeSpan timeout, TimeSpan? pollInterval = null, CancellationToken cancellationToken = default)
    {
        var poll = pollInterval ?? TimeSpan.FromMilliseconds(500);
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline && !cancellationToken.IsCancellationRequested)
        {
            var status = await GetStatusAsync(cancellationToken);
            if (status.IsWaiting) return true;
            if (status.IsComplete) return false;
            if (status.StatusValue is "COMPLETED" or "FAILED" or "TERMINATED" or "TIMED_OUT") return false;
            await Task.Delay(poll, cancellationToken);
        }
        return false;
    }

    /// <summary>
    /// Gracefully stop the agent execution. Sets _stop_requested to true — the
    /// agent's loop exits after the current iteration completes. Status → COMPLETED.
    /// Also unblocks any blocking WaitForMessage calls.
    /// </summary>
    public async Task StopAsync(CancellationToken cancellationToken = default)
        => await _http.StopAgentAsync(_executionId, cancellationToken);

    /// <summary>Gracefully stop the agent execution (synchronous).</summary>
    public void Stop() => StopAsync().GetAwaiter().GetResult();

    /// <summary>
    /// Immediately cancel the agent execution. Status → TERMINATED.
    /// For graceful stop, use <see cref="StopAsync"/> instead.
    /// </summary>
    public async Task CancelAsync(string reason = "", CancellationToken cancellationToken = default)
        => await _http.CancelAgentAsync(_executionId, reason, cancellationToken);

    /// <summary>Immediately cancel the agent execution (synchronous).</summary>
    public void Cancel(string reason = "") => CancelAsync(reason).GetAwaiter().GetResult();

    private static AgentResult BuildResult(JsonNode status, string statusStr, JsonNode? execution = null)
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

        // Extract token usage from the full execution record
        TokenUsage? tokenUsage = null;
        if (execution?["tokenUsage"] is JsonObject tuObj)
        {
            tokenUsage = new TokenUsage(
                PromptTokens:     tuObj["promptTokens"]?.GetValue<int>() ?? 0,
                CompletionTokens: tuObj["completionTokens"]?.GetValue<int>() ?? 0,
                TotalTokens:      tuObj["totalTokens"]?.GetValue<int>() ?? 0
            );
        }

        // Extract finish reason from output (server puts it in output.finishReason)
        FinishReason? finishReason = null;
        var frStr = output?["finishReason"]?.GetValue<string>()?.ToUpperInvariant();
        finishReason = frStr switch
        {
            "STOP"      => Conductor.AI.FinishReason.Stop,
            "LENGTH"    => Conductor.AI.FinishReason.Length,
            "TOOL_CALL" or "TOOL_CALLS" => Conductor.AI.FinishReason.ToolCalls,
            "ERROR"     => Conductor.AI.FinishReason.Error,
            "GUARDRAIL" => Conductor.AI.FinishReason.Guardrail,
            "REJECTED"  => Conductor.AI.FinishReason.Rejected,
            _           => null,
        };

        return new AgentResult
        {
            ExecutionId  = status["executionId"]?.GetValue<string>() ?? "",
            Status       = parsedStatus,
            Output       = outputDict,
            Error        = status["error"]?.GetValue<string>(),
            TokenUsage   = tokenUsage,
            FinishReason = finishReason,
        };
    }
}
