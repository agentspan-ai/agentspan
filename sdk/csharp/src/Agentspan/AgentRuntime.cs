// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;

namespace Agentspan;

/// <summary>
/// Main entry point for running Agentspan agents.
/// </summary>
/// <example>
/// <code>
/// await using var runtime = new AgentRuntime();
/// var result = await runtime.RunAsync(agent, "Hello!");
/// result.PrintResult();
/// </code>
/// </example>
public sealed class AgentRuntime : IAsyncDisposable, IDisposable
{
    private readonly AgentHttpClient _http;
    private WorkerManager? _workers;

    public AgentRuntime(AgentRuntimeOptions? options = null)
    {
        var serverUrl = options?.ServerUrl
            ?? Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL")
            ?? "http://localhost:6767/api";
        var authKey    = options?.AuthKey    ?? Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_KEY");
        var authSecret = options?.AuthSecret ?? Environment.GetEnvironmentVariable("AGENTSPAN_AUTH_SECRET");

        _http = new AgentHttpClient(serverUrl, authKey, authSecret);
    }

    // ── Plan (dry-run compile) ────────────────────────────────

    /// <summary>
    /// Compile an agent to a Conductor WorkflowDef without executing it.
    /// Returns the raw server response including the workflow definition.
    /// Useful for inspecting, debugging, or CI/CD validation.
    /// </summary>
    public JsonNode? Plan(Agent agent) => PlanAsync(agent).GetAwaiter().GetResult();

    /// <summary>
    /// Compile an agent to a Conductor WorkflowDef without executing it.
    /// Returns the raw server response including the workflow definition.
    /// </summary>
    public async Task<JsonNode?> PlanAsync(Agent agent, CancellationToken ct = default)
    {
        var agentConfig = AgentConfigSerializer.SerializeAgent(agent);
        return await _http.CompileAsync(agentConfig, ct);
    }

    // ── Synchronous convenience wrappers ────────────────────

    /// <summary>Run an agent synchronously (blocks until done).</summary>
    public AgentResult Run(Agent agent, string prompt, string? sessionId = null, IEnumerable<string>? media = null)
        => RunAsync(agent, prompt, sessionId, media: media).GetAwaiter().GetResult();

    /// <summary>Start an agent synchronously and return a handle.</summary>
    public AgentHandle Start(Agent agent, string prompt, string? sessionId = null, IEnumerable<string>? media = null)
        => StartAsync(agent, prompt, sessionId, media: media).GetAwaiter().GetResult();

    // ── Async API ────────────────────────────────────────────

    /// <summary>Run an agent and wait for the result.</summary>
    public async Task<AgentResult> RunAsync(
        Agent agent, string prompt, string? sessionId = null,
        IEnumerable<string>? media = null, CancellationToken ct = default)
    {
        var handle = await StartInternalAsync(agent, prompt, sessionId, media, ct);
        var result = await handle.WaitAsync(ct);
        await StopWorkersAsync();
        return result;
    }

    /// <summary>Start an agent asynchronously and return a handle for streaming / HITL.</summary>
    public async Task<AgentHandle> StartAsync(
        Agent agent, string prompt, string? sessionId = null,
        IEnumerable<string>? media = null, CancellationToken ct = default)
    {
        return await StartInternalAsync(agent, prompt, sessionId, media, ct);
    }

    /// <summary>Stream events from an agent execution.</summary>
    public async IAsyncEnumerable<AgentEvent> StreamAsync(
        Agent agent, string prompt, string? sessionId = null,
        IEnumerable<string>? media = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var handle = await StartInternalAsync(agent, prompt, sessionId, media, ct);
        await foreach (var evt in handle.StreamAsync(ct))
            yield return evt;
        await StopWorkersAsync();
    }

    // ── WMQ (Workflow Message Queue) ─────────────────────────

    /// <summary>
    /// Push a message into a running agent's Workflow Message Queue.
    /// The agent must have a <see cref="WaitForMessageTool"/> to receive messages.
    /// Requires conductor.workflow-message-queue.enabled=true on the server.
    /// </summary>
    /// <param name="executionId">The running workflow execution ID.</param>
    /// <param name="message">Any JSON-serializable object. Strings are wrapped as {"message": value}.</param>
    public async Task SendMessageAsync(string executionId, object message, CancellationToken ct = default)
        => await _http.SendWorkflowMessageAsync(executionId, message, ct);

    /// <summary>Push a message into a running agent's Workflow Message Queue (synchronous).</summary>
    public void SendMessage(string executionId, object message)
        => SendMessageAsync(executionId, message).GetAwaiter().GetResult();

    // ── Internal ─────────────────────────────────────────────

    private async Task<AgentHandle> StartInternalAsync(
        Agent agent, string prompt, string? sessionId,
        IEnumerable<string>? media, CancellationToken ct)
    {
        // Fresh worker manager per run
        _workers ??= new WorkerManager(_http);
        _workers.RegisterAgentTools(agent);
        _workers.Start();

        var payload      = AgentConfigSerializer.Serialize(agent, prompt, sessionId ?? "", media);
        var executionId  = await _http.StartAsync(payload, ct);
        return new AgentHandle(executionId, _http);
    }

    private async Task StopWorkersAsync()
    {
        if (_workers is not null)
        {
            await _workers.DisposeAsync();
            _workers = null;
        }
    }

    // ── Disposal ─────────────────────────────────────────────

    public async ValueTask DisposeAsync()
    {
        await StopWorkersAsync();
        _http.Dispose();
    }

    public void Dispose() => DisposeAsync().AsTask().GetAwaiter().GetResult();
}

/// <summary>Configuration options for <see cref="AgentRuntime"/>.</summary>
public sealed class AgentRuntimeOptions
{
    public string? ServerUrl  { get; set; }
    public string? AuthKey    { get; set; }
    public string? AuthSecret { get; set; }
}
