// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Agentspan;

// ── WorkerPollLoop (per-task-type) ─────────────────────────

/// <summary>
/// Polls Conductor for a single task type using a Channel-based producer/consumer
/// pattern per the C# SDK design spec.
/// </summary>
internal sealed class WorkerPollLoop : IAsyncDisposable
{
    private readonly AgentHttpClient _http;
    private readonly string _taskName;
    private readonly Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>> _handler;
    private readonly Channel<JsonElement> _taskChannel;
    private readonly CancellationTokenSource _cts = new();
    private readonly ILogger _logger;
    private readonly int _pollIntervalMs;
    private Task? _pollTask;
    private Task? _executeTask;

    internal WorkerPollLoop(
        AgentHttpClient http,
        string taskName,
        Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>> handler,
        int pollIntervalMs = 100,
        ILogger? logger = null)
    {
        _http = http;
        _taskName = taskName;
        _handler = handler;
        _pollIntervalMs = pollIntervalMs;
        _logger = logger ?? NullLogger.Instance;
        _taskChannel = Channel.CreateBounded<JsonElement>(new BoundedChannelOptions(100)
        {
            FullMode = BoundedChannelFullMode.Wait,
        });
    }

    public void Start()
    {
        var ct = _cts.Token;
        _pollTask    = Task.Run(() => PollLoopAsync(ct), ct);
        _executeTask = Task.Run(() => ExecuteLoopAsync(ct), ct);
    }

    private async Task PollLoopAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(_pollIntervalMs));
        while (await timer.WaitForNextTickAsync(ct))
        {
            try
            {
                var rawTask = await _http.PollTaskRawAsync(_taskName, ct);
                if (rawTask is not null)
                    await _taskChannel.Writer.WriteAsync(rawTask.Value, ct);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Poll error for task {TaskName}", _taskName);
            }
        }
    }

    private async Task ExecuteLoopAsync(CancellationToken ct)
    {
        await foreach (var task in _taskChannel.Reader.ReadAllAsync(ct))
        {
            string taskId = "";
            string workflowId = "";
            try
            {
                taskId     = task.TryGetProperty("taskId", out var tid) ? tid.GetString()! : "";
                workflowId = task.TryGetProperty("workflowInstanceId", out var wid) ? wid.GetString()! : "";

                // Extract input data, strip internal keys
                var inputData = ExtractInputData(task);
                var toolCtx   = ExtractToolContext(task);

                // Credential resolution (future: inject into env vars)
                // Currently credentials are handled server-side via the credential store.

                var result = await _handler(inputData, toolCtx);

                // Wrap primitives — Conductor expects outputData as an object
                object outputData = result switch
                {
                    null      => new { result = (object?)null },
                    string s  => new { result = s },
                    int i     => new { result = i },
                    long l    => new { result = l },
                    double d  => new { result = d },
                    bool b    => new { result = b },
                    _         => result,
                };

                await _http.ReportTaskSuccessAsync(taskId, workflowId, outputData, ct);
            }
            catch (TerminalToolException ex)
            {
                await _http.ReportTaskFailureAsync(taskId, workflowId, ex.Message, terminal: true, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Worker execution error for {TaskName}", _taskName);
                await _http.ReportTaskFailureAsync(taskId, workflowId, ex.Message, terminal: false, ct);
            }
        }
    }

    private static Dictionary<string, JsonElement> ExtractInputData(JsonElement task)
    {
        var dict = new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
        if (!task.TryGetProperty("inputData", out var inputData)) return dict;

        // Strip internal keys
        var internalKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            { "__agentspan_ctx__", "_agent_state", "method" };

        foreach (var prop in inputData.EnumerateObject())
        {
            if (!internalKeys.Contains(prop.Name))
                dict[prop.Name] = prop.Value.Clone();
        }
        return dict;
    }

    private static ToolContext? ExtractToolContext(JsonElement task)
    {
        if (!task.TryGetProperty("inputData", out var inputData)) return null;
        if (!inputData.TryGetProperty("__agentspan_ctx__", out var ctxEl)) return null;

        try
        {
            return JsonSerializer.Deserialize<ToolContext>(ctxEl.GetRawText(), AgentspanJson.Options);
        }
        catch { return null; }
    }

    public async ValueTask DisposeAsync()
    {
        _cts.Cancel();
        _taskChannel.Writer.TryComplete();
        try { if (_pollTask is not null)    await _pollTask; }    catch (OperationCanceledException) { }
        try { if (_executeTask is not null) await _executeTask; } catch (OperationCanceledException) { }
        _cts.Dispose();
    }
}

// ── WorkerManager ──────────────────────────────────────────

/// <summary>
/// Registers all tool workers discovered from the agent tree and manages their lifecycle.
/// </summary>
internal sealed class WorkerManager : IAsyncDisposable
{
    private readonly AgentHttpClient _http;
    private readonly List<WorkerPollLoop> _workers = [];

    public WorkerManager(AgentHttpClient http) => _http = http;

    public void RegisterTools(IEnumerable<ToolDef> tools)
    {
        foreach (var tool in tools)
        {
            if (tool.Handler is null) continue;
            if (_workers.Any(w => w is WorkerPollLoop wpl)) { /* check duplicate by name below */ }

            var handler = tool.Handler;
            var loop = new WorkerPollLoop(_http, tool.Name, handler);
            _workers.Add(loop);
        }
    }

    public void RegisterGuardrails(IEnumerable<GuardrailDef> guardrails)
    {
        foreach (var g in guardrails)
        {
            if (g.Handler is null) continue;
            var handler = g.Handler;
            var loop = new WorkerPollLoop(_http, g.Name, async (args, _ctx) =>
            {
                string content = args.TryGetValue("content", out var el) ? el.GetString() ?? "" : "";
                var result = await handler(content);
                return (object)new Dictionary<string, object>
                {
                    ["passed"]      = result.Passed,
                    ["message"]     = result.Message ?? "",
                    ["fixedOutput"] = result.FixedOutput ?? "",
                };
            });
            _workers.Add(loop);
        }
    }

    public void RegisterAgentTools(Agent agent)
    {
        RegisterTools(agent.Tools);
        RegisterGuardrails(agent.Guardrails);
        foreach (var sub in agent.Agents)
            RegisterAgentTools(sub);
        if (agent.Router is not null)
            RegisterAgentTools(agent.Router);
    }

    public void Start()
    {
        foreach (var w in _workers)
            w.Start();
    }

    public async Task StopAsync()
    {
        foreach (var w in _workers)
            await w.DisposeAsync();
        _workers.Clear();
    }

    public async ValueTask DisposeAsync() => await StopAsync();
}
