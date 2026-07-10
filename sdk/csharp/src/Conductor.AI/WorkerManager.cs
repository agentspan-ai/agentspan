// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json;
using System.Text.Json.Nodes;
using Conductor.Api;
using Conductor.Client;
using Conductor.Client.Models;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Newtonsoft.Json;
using Task = Conductor.Client.Models.Task;

namespace Conductor.AI;

// ── WorkerPollLoop (per-task-type) ─────────────────────────

/// <summary>
/// Polls Conductor for a single task type using the conductor-csharp TaskResourceApi.
/// </summary>
internal sealed class WorkerPollLoop : IAsyncDisposable
{
    private readonly TaskResourceApi _taskClient;
    private readonly AgentClient _http;
    private readonly string _taskName;
    private readonly string? _domain;
    private readonly Func<Dictionary<string, JsonElement>, ToolContext?, System.Threading.Tasks.Task<object?>> _handler;
    private readonly CancellationTokenSource _cts = new();
    private readonly ILogger _logger;
    private readonly int _pollIntervalMs;
    private readonly int _threadCount;
    private readonly string[] _credentialNames;
    private readonly List<System.Threading.Tasks.Task> _pollTasks = [];

    internal WorkerPollLoop(
        TaskResourceApi taskClient,
        AgentClient http,
        string taskName,
        Func<Dictionary<string, JsonElement>, ToolContext?, System.Threading.Tasks.Task<object?>> handler,
        int pollIntervalMs = 100,
        int threadCount = 1,
        ILogger? logger = null,
        string[]? credentialNames = null,
        string? domain = null)
    {
        _taskClient      = taskClient;
        _http            = http;
        _taskName        = taskName;
        _domain          = domain;
        _handler         = handler;
        _pollIntervalMs  = pollIntervalMs > 0 ? pollIntervalMs : 100;
        _threadCount     = threadCount > 0 ? threadCount : 1;
        _logger          = logger ?? NullLogger.Instance;
        _credentialNames = credentialNames ?? [];
    }

    public void Start()
    {
        var ct = _cts.Token;
        // Spawn `_threadCount` concurrent poll loops so a slow handler on one
        // thread doesn't stall sibling tasks of the same type.
        for (int i = 0; i < _threadCount; i++)
            _pollTasks.Add(System.Threading.Tasks.Task.Run(() => PollLoopAsync(ct), ct));
    }

    private async System.Threading.Tasks.Task PollLoopAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(_pollIntervalMs));
        while (await timer.WaitForNextTickAsync(ct))
        {
            try
            {
                Task? task = await _taskClient.PollAsync(
                    _taskName,
                    workerid: Environment.MachineName,
                    domain: _domain);

                if (task is not null)
                    await ExecuteAsync(task, ct);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Poll error for task {TaskName}", _taskName);
            }
        }
    }

    private async System.Threading.Tasks.Task ExecuteAsync(Task task, CancellationToken ct)
    {
        try
        {
            var inputData = ConvertInputData(task.InputData);
            var toolCtx   = ExtractToolContext(inputData);

            // Strip internal keys from the handler-visible input
            var handlerInput = inputData
                .Where(kv => !string.Equals(kv.Key, "__agentspan_ctx__", StringComparison.OrdinalIgnoreCase)
                          && !string.Equals(kv.Key, "_agent_state",      StringComparison.OrdinalIgnoreCase)
                          && !string.Equals(kv.Key, "method",            StringComparison.OrdinalIgnoreCase))
                .ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.OrdinalIgnoreCase);

            // Resolve and inject credentials via the centralized helper so the
            // mutation + invocation + restoration is atomic under a single
            // process-wide lock. See docs/design/secret-injection-contract.md.
            // Tier-2 (env-injection) path; tier-1 (explicit-key) lands when the
            // user-facing API exposes a `credentials` parameter to agent factories.
            // Embedded: the host resolves the worker's declared TaskDef.runtimeMetadata secret names
            // at poll time and delivers the values on the wire-only Task.RuntimeMetadata (never
            // persisted). Prefer that map; otherwise fall back to the native token-pull.
            var resolvedCredentials = ReadRuntimeMetadata(task);
            if (resolvedCredentials.Count == 0 && _credentialNames.Length > 0)
            {
                var creds = await _http.ResolveCredentialsAsync(
                    toolCtx?.ExecutionToken, _credentialNames, ct);
                foreach (var (k, v) in creds)
                    resolvedCredentials[k] = v;
            }

            // Tier-1 (explicit accessor): populate the ambient credential scope so
            // tool code can read resolved credentials via ToolContext.GetCredential /
            // Secrets.Get without relying on process-env injection. Tier-2 (env
            // injection) below remains for framework-passthrough tools.
            object? result;
            using (CredentialScope.Begin(resolvedCredentials))
            {
                result = await CredentialInjection.InjectViaEnvAsync<object?>(
                    resolvedCredentials,
                    () => _handler(handlerInput, toolCtx),
                    ct);
            }

            // Wrap primitives — Conductor expects outputData as an object
            object outputData = result switch
            {
                null     => new { result = (object?)null },
                string s => new { result = s },
                int i    => new { result = i },
                long l   => new { result = l },
                double d => new { result = d },
                bool b   => new { result = b },
                _        => result,
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
                    var wrapper = new Dictionary<string, object?> { ["_state_updates"] = state };
                    var resultJson = System.Text.Json.JsonSerializer.Serialize(outputData, AgentspanJson.Options);
                    var resultNode = JsonNode.Parse(resultJson);
                    if (resultNode is JsonObject obj)
                        foreach (var kv in obj)
                            wrapper[kv.Key] = kv.Value?.DeepClone();
                    else
                        wrapper["result"] = outputData;
                    outputData = wrapper;
                }
            }

            using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var taskResult = new TaskResult(
                workflowInstanceId: task.WorkflowInstanceId,
                taskId: task.TaskId)
            {
                Status     = TaskResult.StatusEnum.COMPLETED,
                OutputData = ToNewtonsoftDict(outputData),
            };
            await _taskClient.UpdateTaskAsync(taskResult);
        }
        catch (TerminalToolException ex)
        {
            using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var taskResult = new TaskResult(
                workflowInstanceId: task.WorkflowInstanceId,
                taskId: task.TaskId)
            {
                Status                = TaskResult.StatusEnum.FAILEDWITHTERMINALERROR,
                ReasonForIncompletion = ex.Message,
            };
            await _taskClient.UpdateTaskAsync(taskResult);
        }
        catch (Exception ex) when (
            ex is CredentialNotFoundException
               or CredentialAuthException
               or CredentialRateLimitException
               or CredentialServiceException)
        {
            // Credential failures are configuration issues — non-retryable.
            // Marking as terminal so the workflow surfaces the cause immediately
            // instead of burning retries on a broken config.
            _logger.LogError(ex, "Credential resolution failed for {TaskName}", _taskName);
            using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var taskResult = new TaskResult(
                workflowInstanceId: task.WorkflowInstanceId,
                taskId: task.TaskId)
            {
                Status                = TaskResult.StatusEnum.FAILEDWITHTERMINALERROR,
                ReasonForIncompletion = $"Credential resolution failed: {ex.Message}",
            };
            await _taskClient.UpdateTaskAsync(taskResult);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker execution error for {TaskName}", _taskName);
            using var reportCts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var taskResult = new TaskResult(
                workflowInstanceId: task.WorkflowInstanceId,
                taskId: task.TaskId)
            {
                Status                = TaskResult.StatusEnum.FAILED,
                ReasonForIncompletion = ex.Message,
            };
            await _taskClient.UpdateTaskAsync(taskResult);
        }
    }

    /// <summary>
    /// Read the host-delivered secret name→value map from <c>Task.RuntimeMetadata</c> (embedded
    /// mode). The host resolves the worker's declared <c>TaskDef.runtimeMetadata</c> names from its
    /// secret store at poll time and injects the values on the wire only — never persisted to task
    /// input (conductor-oss PR #1255). Empty when absent (standalone → the native token-pull).
    /// </summary>
    private static Dictionary<string, string> ReadRuntimeMetadata(Task task)
    {
        var result = new Dictionary<string, string>();
        if (task?.RuntimeMetadata is { Count: > 0 } rm)
        {
            foreach (var (k, v) in rm)
                if (k is not null && v is not null)
                    result[k] = v;
        }
        return result;
    }

    // ── JSON bridges (Newtonsoft ↔ System.Text.Json) ──────────

    /// <summary>Convert conductor-csharp's Newtonsoft-deserialized inputData to STJ JsonElements.</summary>
    private static Dictionary<string, JsonElement> ConvertInputData(Dictionary<string, object>? inputData)
    {
        if (inputData is null || inputData.Count == 0)
            return new Dictionary<string, JsonElement>();

        var json = JsonConvert.SerializeObject(inputData);
        using var doc = System.Text.Json.JsonSerializer.Deserialize<JsonDocument>(json)!;
        var result = new Dictionary<string, JsonElement>(StringComparer.OrdinalIgnoreCase);
        foreach (var prop in doc.RootElement.EnumerateObject())
            result[prop.Name] = prop.Value.Clone();
        return result;
    }

    /// <summary>Convert STJ-serializable output to a Newtonsoft-compatible dict for TaskResult.OutputData.</summary>
    private static Dictionary<string, object> ToNewtonsoftDict(object outputData)
    {
        var json = System.Text.Json.JsonSerializer.Serialize(outputData, AgentspanJson.Options);
        return JsonConvert.DeserializeObject<Dictionary<string, object>>(json)
            ?? new Dictionary<string, object>();
    }

    private static ToolContext? ExtractToolContext(Dictionary<string, JsonElement> inputData)
    {
        ToolContext? ctx = null;
        if (inputData.TryGetValue("__agentspan_ctx__", out var ctxEl))
        {
            try { ctx = System.Text.Json.JsonSerializer.Deserialize<ToolContext>(ctxEl.GetRawText(), AgentspanJson.Options); }
            catch { }
        }

        Dictionary<string, object>? state = null;
        if (inputData.TryGetValue("_agent_state", out var agentStateEl) &&
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
        try { await System.Threading.Tasks.Task.WhenAll(_pollTasks); }
        catch (OperationCanceledException) { }
        catch { /* individual poll loops log their own errors */ }
        _cts.Dispose();
    }
}

// ── WorkerManager ──────────────────────────────────────────

/// <summary>
/// Registers all tool workers discovered from the agent tree and manages their lifecycle.
/// </summary>
internal sealed class WorkerManager : IAsyncDisposable
{
    private readonly AgentClient _http;
    private readonly TaskResourceApi _taskClient;
    private readonly List<WorkerPollLoop> _workers = [];
    private readonly int _pollIntervalMs;
    private readonly int _threadCount;

    public WorkerManager(AgentClient http, Configuration conductorConfig,
        int pollIntervalMs = 100, int threadCount = 1)
    {
        _http           = http;
        _taskClient     = new TaskResourceApi(conductorConfig);
        _pollIntervalMs = pollIntervalMs > 0 ? pollIntervalMs : 100;
        _threadCount    = threadCount > 0 ? threadCount : 1;
    }

    private WorkerPollLoop NewLoop(
        string taskName,
        Func<Dictionary<string, JsonElement>, ToolContext?, System.Threading.Tasks.Task<object?>> handler,
        string[]? credentialNames = null,
        string? domain = null)
        => new(_taskClient, _http, taskName, handler,
               pollIntervalMs: _pollIntervalMs, threadCount: _threadCount,
               credentialNames: credentialNames, domain: domain);

    public void RegisterTools(IEnumerable<ToolDef> tools, string? domain = null)
    {
        foreach (var tool in tools)
        {
            if (tool.Handler is null) continue;
            _workers.Add(NewLoop(tool.Name, tool.Handler,
                credentialNames: tool.Credentials.Length > 0 ? tool.Credentials : null,
                domain: domain));
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

            _workers.Add(NewLoop(g.Name, async (args, _ctx) =>
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
                        ["passed"]          = false,
                        ["message"]         = $"Guardrail error: {ex.Message}",
                        ["on_fail"]         = effectiveOnFailOnEx.ToString().ToLowerInvariant(),
                        ["fixed_output"]    = null,
                        ["guardrail_name"]  = gName,
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
                        ["passed"]          = false,
                        ["message"]         = result.Message ?? "",
                        ["on_fail"]         = effectiveOnFail.ToString().ToLowerInvariant(),
                        ["fixed_output"]    = result.FixedOutput,
                        ["guardrail_name"]  = gName,
                        ["should_continue"] = effectiveOnFail == OnFail.Retry,
                    };
                }

                return (object)new Dictionary<string, object?>
                {
                    ["passed"]          = true,
                    ["message"]         = "",
                    ["on_fail"]         = "pass",
                    ["fixed_output"]    = null,
                    ["guardrail_name"]  = "",
                    ["should_continue"] = false,
                };
            }, domain: domain));
        }
    }

    public void RegisterAgentTools(Agent agent, string? domain = null)
    {
        if (agent.Framework == "skill")
            RegisterSkillWorkers(agent, domain);

        RegisterTools(agent.Tools, domain);
        RegisterGuardrails(agent.Guardrails, domain);
        foreach (var tool in agent.Tools)
            RegisterGuardrails(tool.Guardrails, domain);
        RegisterCallbacks(agent, domain);

        // Local code execution worker — the server adds an execute_code tool to
        // the agent when LocalCodeExecution=true (or CodeExecution is set), but
        // the SDK is responsible for polling and actually running the code.
        // Without this, the LLM's execute_code calls would sit in SCHEDULED
        // forever. Mirrors Java's AgentRuntime.prepareWorkers code-exec branch.
        if (agent.LocalCodeExecution || agent.CodeExecution is not null)
            RegisterLocalCodeExecutionWorker(agent, domain);

        if (agent.Strategy == Strategy.Swarm && agent.Agents.Count > 0)
            RegisterSwarmTransferWorkers(agent, domain);

        if (agent.Strategy == Strategy.Manual && agent.Agents.Count > 0)
            RegisterManualSelectionWorker(agent, domain);

        foreach (var sub in agent.Agents)
            RegisterAgentTools(sub, domain);
        if (agent.Router is not null)
            RegisterAgentTools(agent.Router, domain);

        foreach (var tool in agent.Tools)
        {
            if (tool.ToolType == "agent_tool" && tool.WrappedAgent is not null)
                RegisterAgentTools(tool.WrappedAgent, domain);
        }
    }

    private void RegisterSkillWorkers(Agent agent, string? domain = null)
    {
        foreach (var worker in Skill.CreateSkillWorkers(agent))
        {
            _workers.Add(NewLoop(worker.Name, async (args, _ctx) =>
            {
                var input = args.ToDictionary(
                    kv => kv.Key,
                    kv => JsonElementToObject(kv.Value));
                return await worker.Handler(input);
            }, domain: domain));
        }
    }

    private static object? JsonElementToObject(JsonElement value)
    {
        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString(),
            JsonValueKind.Number when value.TryGetInt64(out var l) => l,
            JsonValueKind.Number when value.TryGetDouble(out var d) => d,
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => null,
            _ => value.GetRawText(),
        };
    }

    private void RegisterLocalCodeExecutionWorker(Agent agent, string? domain)
    {
        var taskName = $"{agent.Name}_execute_code";
        var timeout  = agent.CodeExecution?.Timeout ?? 30;

        _workers.Add(NewLoop(taskName, async (args, _) =>
        {
            string language = "python";
            if (args.TryGetValue("language", out var lang) && lang.ValueKind == JsonValueKind.String)
                language = lang.GetString() ?? "python";

            string code = "";
            if (args.TryGetValue("code", out var c) && c.ValueKind == JsonValueKind.String)
                code = c.GetString() ?? "";

            return await ExecuteLocalCodeAsync(language, code, timeout);
        }, domain: domain));
    }

    private static async Task<object?> ExecuteLocalCodeAsync(string language, string code, int timeoutSeconds)
    {
        // Delegate to the shared LocalCodeExecutor (subprocess + temp file +
        // interpreter table + timeout + cleanup), then map its structured
        // ExecutionResult onto this worker's wire contract. stdout+stderr are
        // combined into "output" to preserve the prior runtime behavior.
        var exec = new LocalCodeExecutor(language: language, timeout: timeoutSeconds);
        var er = await exec.ExecuteAsync(code);

        var result = new Dictionary<string, object?>
        {
            ["output"]    = (er.Output ?? "") + (er.Error ?? ""),
            ["exit_code"] = er.ExitCode,
            ["success"]   = er.Success,
        };
        if (!er.Success)
        {
            result["error"] = er.TimedOut
                ? $"Code execution timed out after {timeoutSeconds}s"
                : !string.IsNullOrEmpty(er.Error) ? er.Error
                : $"Process exited with code {er.ExitCode}";
        }
        return result;
    }

    private void RegisterCallbacks(Agent agent, string? domain = null)
    {
        // before_model / after_model keep their bespoke argument signatures
        // (messages list / llm_result string). Track them so the generic
        // position loop below doesn't double-register the same task name.
        var registered = new HashSet<string>(StringComparer.Ordinal);

        if (agent.BeforeModelCallback is not null)
        {
            var cb = agent.BeforeModelCallback;
            registered.Add("before_model");
            _workers.Add(NewLoop($"{agent.Name}_before_model", (args, _) =>
            {
                List<JsonElement>? messages = null;
                if (args.TryGetValue("messages", out var msgEl) && msgEl.ValueKind == JsonValueKind.Array)
                    messages = msgEl.EnumerateArray().ToList();
                var result = cb(messages);
                return System.Threading.Tasks.Task.FromResult<object?>(result ?? new Dictionary<string, object>());
            }, domain: domain));
        }

        if (agent.AfterModelCallback is not null)
        {
            var cb = agent.AfterModelCallback;
            registered.Add("after_model");
            _workers.Add(NewLoop($"{agent.Name}_after_model", (args, _) =>
            {
                string? llmResult = args.TryGetValue("llm_result", out var resEl) && resEl.ValueKind == JsonValueKind.String
                    ? resEl.GetString()
                    : null;
                var result = cb(llmResult);
                return System.Threading.Tasks.Task.FromResult<object?>(result ?? new Dictionary<string, object>());
            }, domain: domain));
        }

        // Generic kwargs-based callbacks: the agent/tool function callbacks plus
        // any CallbackHandler that overrides a hook. Multiple delegates can target
        // one position (run in order, first non-empty return short-circuits).
        var byPosition =
            new Dictionary<string, List<Func<Dictionary<string, JsonElement>, Dictionary<string, object>?>>>(
                StringComparer.Ordinal);

        void Add(string position, Func<Dictionary<string, JsonElement>, Dictionary<string, object>?>? fn)
        {
            if (fn is null) return;
            if (!byPosition.TryGetValue(position, out var list)) byPosition[position] = list = [];
            list.Add(fn);
        }

        Add("before_agent", agent.BeforeAgentCallback);
        Add("after_agent",  agent.AfterAgentCallback);
        Add("before_tool",  agent.BeforeToolCallback);
        Add("after_tool",   agent.AfterToolCallback);

        foreach (var (position, method) in CallbackHandler.Positions)
            foreach (var handler in agent.Callbacks)
                if (handler.Overrides(method))
                {
                    var h = handler;
                    var m = method;
                    Add(position, kwargs => h.Invoke(m, kwargs));
                }

        foreach (var (position, delegates) in byPosition)
        {
            if (registered.Contains(position)) continue;
            var fns = delegates;
            _workers.Add(NewLoop($"{agent.Name}_{position}", (args, _) =>
            {
                foreach (var fn in fns)
                {
                    var r = fn(args);
                    if (r is { Count: > 0 }) return System.Threading.Tasks.Task.FromResult<object?>(r);
                }
                return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>());
            }, domain: domain));
        }
    }

    private void RegisterSwarmTransferWorkers(Agent agent, string? domain = null)
    {
        var allNames = new List<string> { agent.Name };
        allNames.AddRange(agent.Agents.Select(a => a.Name));

        var registered = new HashSet<string>();
        foreach (var sourceName in allNames)
        {
            foreach (var targetName in allNames)
            {
                if (sourceName == targetName) continue;
                var toolName = $"{sourceName}_transfer_to_{targetName}";
                if (!registered.Add(toolName)) continue;
                _workers.Add(NewLoop(toolName,
                    (_, _) => System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>()),
                    domain: domain));
            }
        }

        foreach (var name in allNames)
        {
            _workers.Add(NewLoop($"{name}_check_transfer", (args, _) =>
            {
                if (args.TryGetValue("tool_calls", out var tcEl) && tcEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var tc in tcEl.EnumerateArray())
                    {
                        var tcName = tc.TryGetProperty("name", out var np) ? np.GetString() ?? "" : "";
                        if (tcName.Contains("_transfer_to_"))
                        {
                            var transferTarget = tcName.Split("_transfer_to_", 2)[1];
                            return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>
                            {
                                ["is_transfer"] = true,
                                ["transfer_to"] = transferTarget,
                            });
                        }
                    }
                }
                return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>
                {
                    ["is_transfer"] = false,
                    ["transfer_to"] = "",
                });
            }, domain: domain));
        }

        var nameToIdx = new Dictionary<string, string> { [agent.Name] = "0" };
        for (int i = 0; i < agent.Agents.Count; i++)
            nameToIdx[agent.Agents[i].Name] = (i + 1).ToString();
        var idxToName         = nameToIdx.ToDictionary(kv => kv.Value, kv => kv.Key);
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
            (val.ValueKind == JsonValueKind.String && val.GetString()?.Trim().ToLower() == "true");

        var handoffConditions = agent.Handoffs;

        _workers.Add(NewLoop($"{agent.Name}_handoff_check", (args, _) =>
        {
            var activeAgent = args.TryGetValue("active_agent", out var ae) ? ae.GetString() ?? "0" : "0";
            var isTransfer  = args.TryGetValue("is_transfer",  out var it) && IsTransferTruthy(it);
            var transferTo  = args.TryGetValue("transfer_to",  out var tt) ? tt.GetString() ?? "" : "";

            // Priority 1: explicit transfer tool was called.
            if (isTransfer && !string.IsNullOrEmpty(transferTo) && IsAllowed(activeAgent, transferTo))
            {
                var targetIdx = nameToIdx.TryGetValue(transferTo, out var ti) ? ti : activeAgent;
                if (targetIdx != activeAgent)
                    return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>
                    {
                        ["active_agent"] = targetIdx,
                        ["handoff"]      = true,
                    });
            }

            // Priority 2: condition-based handoffs (fallback). Mirrors Python's
            // handoff_check_worker — evaluate each trigger against the context.
            if (handoffConditions.Count > 0)
            {
                var context = new Dictionary<string, object?>
                {
                    ["result"]      = args.TryGetValue("result", out var rEl) ? rEl.ToString() : "",
                    ["messages"]    = args.TryGetValue("conversation", out var cEl) ? cEl.ToString() : "",
                    ["tool_name"]   = "",
                    ["tool_result"] = "",
                };
                foreach (var cond in handoffConditions)
                {
                    if (!cond.ShouldHandoff(context)) continue;
                    if (!IsAllowed(activeAgent, cond.Target)) continue;
                    var targetIdx = nameToIdx.TryGetValue(cond.Target, out var ci) ? ci : activeAgent;
                    if (targetIdx != activeAgent)
                        return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>
                        {
                            ["active_agent"] = targetIdx,
                            ["handoff"]      = true,
                        });
                }
            }

            return System.Threading.Tasks.Task.FromResult<object?>(new Dictionary<string, object>
            {
                ["active_agent"] = activeAgent,
                ["handoff"]      = false,
            });
        }, domain: domain));
    }

    private void RegisterManualSelectionWorker(Agent agent, string? domain = null)
    {
        var nameToIdx = agent.Agents.Select((a, i) => (a.Name, Index: i.ToString()))
                                    .ToDictionary(t => t.Name, t => t.Index);

        _workers.Add(NewLoop($"{agent.Name}_process_selection", (args, _) =>
        {
            string selected = "0";
            if (args.TryGetValue("human_output", out var ho))
            {
                if (ho.ValueKind == JsonValueKind.Object)
                {
                    string? agentName = null;
                    if (ho.TryGetProperty("selected", out var sp)) agentName = sp.GetString();
                    else if (ho.TryGetProperty("agent", out var ap)) agentName = ap.GetString();

                    if (agentName != null && nameToIdx.TryGetValue(agentName, out var idx))
                        selected = idx;
                    else if (agentName != null)
                        selected = agentName;
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
            return System.Threading.Tasks.Task.FromResult<object?>(
                new Dictionary<string, object> { ["selected"] = selected });
        }, domain: domain));
    }

    public void Start()
    {
        foreach (var w in _workers)
            w.Start();
    }

    public async System.Threading.Tasks.Task StopAsync()
    {
        foreach (var w in _workers)
            await w.DisposeAsync();
        _workers.Clear();
    }

    public async ValueTask DisposeAsync() => await StopAsync();
}
