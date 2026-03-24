using System.Text.Json;

namespace Agentspan;

public sealed class WorkerManager : IAsyncDisposable, IDisposable
{
    private readonly AgentHttpClient _client;
    private readonly AgentConfig _config;
    private readonly Dictionary<string, Func<Dictionary<string, object?>, Task<Dictionary<string, object?>>>> _workers = new();
    private readonly List<Task> _pollingTasks = new();
    private readonly CancellationTokenSource _cts = new();
    private bool _started;

    public WorkerManager(AgentHttpClient client, AgentConfig config)
    {
        _client = client;
        _config = config;
    }

    public void RegisterWorker(string taskType, Func<Dictionary<string, object?>, Dictionary<string, object?>> func)
    {
        _workers[taskType] = input => Task.FromResult(func(input));
    }

    public void RegisterWorkerAsync(string taskType, Func<Dictionary<string, object?>, Task<Dictionary<string, object?>>> func)
    {
        _workers[taskType] = func;
    }

    public void Start()
    {
        if (_started) return;
        _started = true;
        foreach (var (taskType, func) in _workers)
        {
            var t = taskType; // capture
            var f = func;
            var task = Task.Run(() => PollLoopAsync(t, f, _cts.Token));
            _pollingTasks.Add(task);
        }
    }

    public void Stop() => _cts.Cancel();

    private async Task PollLoopAsync(
        string taskType,
        Func<Dictionary<string, object?>, Task<Dictionary<string, object?>>> func,
        CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var task = await _client.PollTaskAsync(taskType, ct);
                if (task != null)
                {
                    var taskId = task.GetValueOrDefault("taskId")?.ToString() ?? "";
                    var wfId = task.GetValueOrDefault("workflowInstanceId")?.ToString() ?? "";
                    var inputData = GetInputData(task);

                    try
                    {
                        var output = await func(inputData);
                        await _client.UpdateTaskAsync(taskId, wfId, "COMPLETED", output, ct);
                    }
                    catch (Exception ex)
                    {
                        var errOutput = new Dictionary<string, object?> { ["error"] = ex.Message };
                        await _client.UpdateTaskAsync(taskId, wfId, "FAILED_WITH_TERMINAL_ERROR", errOutput, ct);
                    }
                }
                else
                {
                    await Task.Delay(_config.WorkerPollIntervalMs, ct);
                }
            }
            catch (OperationCanceledException) { break; }
            catch { await Task.Delay(_config.WorkerPollIntervalMs, ct); }
        }
    }

    private static Dictionary<string, object?> GetInputData(Dictionary<string, object?> task)
    {
        if (task.TryGetValue("inputData", out var raw) && raw is System.Text.Json.JsonElement je)
            return je.Deserialize<Dictionary<string, object?>>() ?? new();
        return new Dictionary<string, object?>();
    }

    public void Dispose() => Stop();

    public ValueTask DisposeAsync()
    {
        Stop();
        return ValueTask.CompletedTask;
    }
}
