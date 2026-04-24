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
    private readonly string? _domain;
    private readonly Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>> _handler;
    private readonly Channel<JsonElement> _taskChannel;
    private readonly CancellationTokenSource _cts = new();
    private readonly ILogger _logger;
    private readonly int _pollIntervalMs;
    private readonly string[] _credentialNames;
    private Task? _pollTask;
    private Task? _executeTask;

    internal WorkerPollLoop(
        AgentHttpClient http,
        string taskName,
        Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>> handler,
        int pollIntervalMs = 100,
        ILogger? logger = null,
        string[]? credentialNames = null,
        string? domain = null)
    {
        _http = http;
        _taskName = taskName;
        _domain = domain;
        _handler = handler;
        _pollIntervalMs = pollIntervalMs;
        _logger = logger ?? NullLogger.Instance;
        _credentialNames = credentialNames ?? [];
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
                var rawTask = await _http.PollTaskRawAsync(_taskName, _domain, ct);
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

                // Resolve and inject credentials as env vars for the duration of this call
                var injectedKeys = new List<string>();
                if (_credentialNames.Length > 0)
                {
                    var creds = await _http.ResolveCredentialsAsync(toolCtx?.ExecutionToken, _credentialNames, ct);
                    foreach (var (k, v) in creds)
                    {
                        Environment.SetEnvironmentVariable(k, v);
                        injectedKeys.Add(k);
                    }
                }

                object? result;
                try
                {
                    result = await _handler(inputData, toolCtx);
                }
                finally
                {
                    // Clean up injected env vars
                    foreach (var k in injectedKeys)
                        Environment.SetEnvironmentVariable(k, null);
                }

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

                // Include state updates so the server can persist shared state
                if (toolCtx?.State is { Count: > 0 } state)
                {
                    if (outputData is Dictionary<string, object> outDict)
                        outDict["_state_updates"] = state;
                    else if (outputData is Dictionary<string, object?> outDictN)
                        outDictN["_state_updates"] = state;
                    else
                    {
                        // Wrap in a dictionary with both result and state
                        var wrapper = new Dictionary<string, object?> { ["_state_updates"] = state };
                        // Re-serialize result into wrapper
                        var resultJson = JsonSerializer.Serialize(outputData, AgentspanJson.Options);
                        var resultNode = JsonNode.Parse(resultJson);
                        if (resultNode is JsonObject obj)
                        {
                            foreach (var kv in obj)
                                wrapper[kv.Key] = kv.Value?.DeepClone();
                        }
                        else
                        {
                            wrapper["result"] = outputData;
                        }
                        outputData = wrapper;
                    }
                }

                // Use a fresh token for reporting so that worker shutdown (ct cancellation)
                // doesn't prevent the completed task from being acknowledged on the server.
                using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                await _http.ReportTaskSuccessAsync(taskId, workflowId, outputData, reportCts.Token);
            }
            catch (TerminalToolException ex)
            {
                using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                await _http.ReportTaskFailureAsync(taskId, workflowId, ex.Message, terminal: true, reportCts.Token);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Worker execution error for {TaskName}", _taskName);
                using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                await _http.ReportTaskFailureAsync(taskId, workflowId, ex.Message, terminal: false, reportCts.Token);
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

        // Extract base context (execution token etc.)
        ToolContext? ctx = null;
        if (inputData.TryGetProperty("__agentspan_ctx__", out var ctxEl))
        {
            try { ctx = JsonSerializer.Deserialize<ToolContext>(ctxEl.GetRawText(), AgentspanJson.Options); }
            catch { }
        }

        // Extract shared state from _agent_state (persisted across tool calls by the server)
        Dictionary<string, object>? state = null;
        if (inputData.TryGetProperty("_agent_state", out var agentStateEl) &&
            agentStateEl.ValueKind == JsonValueKind.Object)
        {
            state = new Dictionary<string, object>();
            foreach (var prop in agentStateEl.EnumerateObject())
                state[prop.Name] = prop.Value.Clone();
        }

        if (ctx is null && state is null) return null;

        return (ctx ?? new ToolContext()) with { State = state ?? ctx?.State };
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

    public void RegisterTools(IEnumerable<ToolDef> tools, string? domain = null)
    {
        foreach (var tool in tools)
        {
            if (tool.Handler is null) continue;

            var handler = tool.Handler;
            var loop = new WorkerPollLoop(_http, tool.Name, handler,
                credentialNames: tool.Credentials.Length > 0 ? tool.Credentials : null,
                domain: domain);
            _workers.Add(loop);
        }
    }

    public void RegisterGuardrails(IEnumerable<GuardrailDef> guardrails, string? domain = null)
    {
        foreach (var g in guardrails)
        {
            if (g.Handler is null) continue;
            var handler    = g.Handler;
            var onFail     = g.OnFail;
            var maxRetries = g.MaxRetries;
            var gName      = g.Name;

            var loop = new WorkerPollLoop(_http, g.Name, async (args, _ctx) =>
            {
                string content = args.TryGetValue("content", out var contentEl)
                    ? (contentEl.ValueKind == JsonValueKind.String
                        ? contentEl.GetString() ?? ""
                        : contentEl.GetRawText())
                    : "";

                int iteration = args.TryGetValue("iteration", out var iterEl) &&
                                iterEl.ValueKind == JsonValueKind.Number
                    ? iterEl.GetInt32()
                    : 0;

                GuardrailResult result;
                try
                {
                    result = await handler(content);
                }
                catch (Exception ex)
                {
                    var effectiveOnFailOnEx = onFail;
                    if (effectiveOnFailOnEx == OnFail.Retry && iteration >= maxRetries)
                        effectiveOnFailOnEx = OnFail.Raise;
                    return (object)new Dictionary<string, object?>
                    {
                        ["passed"]         = false,
                        ["message"]        = $"Guardrail error: {ex.Message}",
                        ["on_fail"]        = effectiveOnFailOnEx.ToString().ToLowerInvariant(),
                        ["fixed_output"]   = null,
                        ["guardrail_name"] = gName,
                        ["should_continue"] = effectiveOnFailOnEx == OnFail.Retry,
                    };
                }

                if (!result.Passed)
                {
                    var effectiveOnFail = onFail;
                    if (effectiveOnFail == OnFail.Retry && iteration >= maxRetries)
                        effectiveOnFail = OnFail.Raise;
                    if (effectiveOnFail == OnFail.Fix && result.FixedOutput is null)
                        effectiveOnFail = OnFail.Raise;

                    return (object)new Dictionary<string, object?>
                    {
                        ["passed"]         = false,
                        ["message"]        = result.Message ?? "",
                        ["on_fail"]        = effectiveOnFail.ToString().ToLowerInvariant(),
                        ["fixed_output"]   = result.FixedOutput,
                        ["guardrail_name"] = gName,
                        ["should_continue"] = effectiveOnFail == OnFail.Retry,
                    };
                }

                return (object)new Dictionary<string, object?>
                {
                    ["passed"]         = true,
                    ["message"]        = "",
                    ["on_fail"]        = "pass",
                    ["fixed_output"]   = null,
                    ["guardrail_name"] = "",
                    ["should_continue"] = false,
                };
            }, domain: domain);
            _workers.Add(loop);
        }
    }

    public void RegisterAgentTools(Agent agent, string? domain = null)
    {
        RegisterTools(agent.Tools, domain);
        RegisterGuardrails(agent.Guardrails, domain);
        // Also register guardrails attached directly to individual tools
        foreach (var tool in agent.Tools)
            RegisterGuardrails(tool.Guardrails, domain);
        RegisterCallbacks(agent, domain);

        if (agent.Strategy == Strategy.Swarm && agent.Agents.Count > 0)
            RegisterSwarmTransferWorkers(agent, domain);

        if (agent.Strategy == Strategy.Manual && agent.Agents.Count > 0)
            RegisterManualSelectionWorker(agent, domain);

        foreach (var sub in agent.Agents)
            RegisterAgentTools(sub, domain);
        if (agent.Router is not null)
            RegisterAgentTools(agent.Router, domain);

        // Recurse into agents wrapped as AgentTool
        foreach (var tool in agent.Tools)
        {
            if (tool.ToolType == "agent_tool" && tool.WrappedAgent is not null)
                RegisterAgentTools(tool.WrappedAgent, domain);
        }
    }

    private void RegisterCallbacks(Agent agent, string? domain = null)
    {
        if (agent.BeforeModelCallback is not null)
        {
            var cb = agent.BeforeModelCallback;
            var taskName = $"{agent.Name}_before_model";
            _workers.Add(new WorkerPollLoop(_http, taskName, (args, _) =>
            {
                List<JsonElement>? messages = null;
                if (args.TryGetValue("messages", out var msgEl) && msgEl.ValueKind == JsonValueKind.Array)
                    messages = msgEl.EnumerateArray().ToList();
                var result = cb(messages);
                return Task.FromResult<object?>(result ?? new Dictionary<string, object>());
            }, domain: domain));
        }

        if (agent.AfterModelCallback is not null)
        {
            var cb = agent.AfterModelCallback;
            var taskName = $"{agent.Name}_after_model";
            _workers.Add(new WorkerPollLoop(_http, taskName, (args, _) =>
            {
                string? llmResult = args.TryGetValue("llm_result", out var resEl) && resEl.ValueKind == JsonValueKind.String
                    ? resEl.GetString()
                    : null;
                var result = cb(llmResult);
                return Task.FromResult<object?>(result ?? new Dictionary<string, object>());
            }, domain: domain));
        }
    }

    /// <summary>
    /// Register no-op transfer workers + check_transfer workers for every agent in a Swarm.
    /// Transfer workers: {sourceName}_transfer_to_{targetName} — no-op, returns {}
    /// Check-transfer workers: {agentName}_check_transfer — inspects toolCalls to detect handoffs
    /// </summary>
    private void RegisterSwarmTransferWorkers(Agent agent, string? domain = null)
    {
        var allNames = new List<string> { agent.Name };
        allNames.AddRange(agent.Agents.Select(a => a.Name));

        // Register no-op transfer workers
        var registered = new HashSet<string>();
        foreach (var sourceName in allNames)
        {
            foreach (var targetName in allNames)
            {
                if (sourceName == targetName) continue;
                var toolName = $"{sourceName}_transfer_to_{targetName}";
                if (!registered.Add(toolName)) continue;

                var loop = new WorkerPollLoop(_http, toolName,
                    (_, _) => Task.FromResult<object?>(new Dictionary<string, object>()),
                    domain: domain);
                _workers.Add(loop);
            }
        }

        // Register check_transfer workers for each agent in the swarm
        foreach (var name in allNames)
        {
            var checkTaskName = $"{name}_check_transfer";
            var loop = new WorkerPollLoop(_http, checkTaskName,
                (args, _) =>
                {
                    // tool_calls is a list of {name, ...} objects
                    if (args.TryGetValue("tool_calls", out var tcEl))
                    {
                        if (tcEl.ValueKind == JsonValueKind.Array)
                        {
                            foreach (var tc in tcEl.EnumerateArray())
                            {
                                var tcName = tc.TryGetProperty("name", out var np)
                                    ? np.GetString() ?? ""
                                    : "";
                                if (tcName.Contains("_transfer_to_"))
                                {
                                    var transferTarget = tcName.Split("_transfer_to_", 2)[1];
                                    return Task.FromResult<object?>(new Dictionary<string, object>
                                    {
                                        ["is_transfer"] = true,
                                        ["transfer_to"] = transferTarget,
                                    });
                                }
                            }
                        }
                    }
                    return Task.FromResult<object?>(new Dictionary<string, object>
                    {
                        ["is_transfer"] = false,
                        ["transfer_to"] = "",
                    });
                }, domain: domain);
            _workers.Add(loop);
        }

        // Register handoff_check worker for the parent swarm agent
        // Maps agent names to indices: parent=0, sub[0]=1, sub[1]=2, ...
        var nameToIdx = new Dictionary<string, string> { [agent.Name] = "0" };
        for (int i = 0; i < agent.Agents.Count; i++)
            nameToIdx[agent.Agents[i].Name] = (i + 1).ToString();
        var idxToName = nameToIdx.ToDictionary(kv => kv.Value, kv => kv.Key);
        var allowedTransitions = agent.AllowedTransitions;

        bool IsAllowed(string sourceIdx, string targetName)
        {
            if (allowedTransitions is null) return true;
            var sourceName = idxToName.TryGetValue(sourceIdx, out var sn) ? sn : "";
            return allowedTransitions.TryGetValue(sourceName, out var targets)
                && targets.Contains(targetName);
        }

        bool IsTransferTruthy(JsonElement val) =>
            val.ValueKind == JsonValueKind.True ||
            (val.ValueKind == JsonValueKind.String &&
             val.GetString()?.Trim().ToLower() == "true");

        var handoffTaskName = $"{agent.Name}_handoff_check";
        var handoffLoop = new WorkerPollLoop(_http, handoffTaskName, (args, _) =>
        {
            var activeAgent  = args.TryGetValue("active_agent",  out var ae) ? ae.GetString() ?? "0" : "0";
            var isTransfer   = args.TryGetValue("is_transfer",   out var it) && IsTransferTruthy(it);
            var transferTo   = args.TryGetValue("transfer_to",   out var tt) ? tt.GetString() ?? "" : "";

            if (isTransfer && !string.IsNullOrEmpty(transferTo))
            {
                if (IsAllowed(activeAgent, transferTo))
                {
                    var targetIdx = nameToIdx.TryGetValue(transferTo, out var ti) ? ti : activeAgent;
                    if (targetIdx != activeAgent)
                        return Task.FromResult<object?>(new Dictionary<string, object>
                        {
                            ["active_agent"] = targetIdx,
                            ["handoff"]      = true,
                        });
                }
            }

            return Task.FromResult<object?>(new Dictionary<string, object>
            {
                ["active_agent"] = activeAgent,
                ["handoff"]      = false,
            });
        }, domain: domain);
        _workers.Add(handoffLoop);
    }

    /// <summary>
    /// Register a process_selection worker for Manual strategy.
    /// Converts human agent-name selection to agent index required by the server.
    /// </summary>
    private void RegisterManualSelectionWorker(Agent agent, string? domain = null)
    {
        var taskName   = $"{agent.Name}_process_selection";
        var nameToIdx  = agent.Agents.Select((a, i) => (a.Name, Index: i.ToString()))
                                     .ToDictionary(t => t.Name, t => t.Index);

        var loop = new WorkerPollLoop(_http, taskName, (args, _) =>
        {
            string selected = "0";

            if (args.TryGetValue("human_output", out var ho))
            {
                if (ho.ValueKind == JsonValueKind.Object)
                {
                    // {"selected": "writer"} or {"agent": "writer"}
                    string? agentName = null;
                    if (ho.TryGetProperty("selected", out var sp)) agentName = sp.GetString();
                    else if (ho.TryGetProperty("agent",    out var ap)) agentName = ap.GetString();

                    if (agentName != null && nameToIdx.TryGetValue(agentName, out var idx))
                        selected = idx;
                    else if (agentName != null)
                        selected = agentName; // pass through if already an index
                }
                else if (ho.ValueKind == JsonValueKind.String)
                {
                    var sv = ho.GetString() ?? "0";
                    selected = nameToIdx.TryGetValue(sv, out var idx2) ? idx2 : sv;
                }
                else if (ho.ValueKind == JsonValueKind.Number)
                {
                    selected = ho.GetInt32().ToString();
                }
            }

            return Task.FromResult<object?>(new Dictionary<string, object> { ["selected"] = selected });
        }, domain: domain);

        _workers.Add(loop);
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
