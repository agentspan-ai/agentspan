// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Net.Http;
using System.Text.Json.Nodes;
using Xunit;

namespace Agentspan.E2eTests;

/// <summary>
/// Shared fixture that checks server availability once per test collection.
/// Tests skip automatically when the server is unreachable.
/// </summary>
public sealed class E2eFixture : IAsyncLifetime
{
    private static readonly string ServerBase =
        (Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:6767/api")
        .TrimEnd('/').Replace("/api", "");

    public bool ServerAvailable { get; private set; }

    public async Task InitializeAsync()
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
        try
        {
            var resp = await http.GetAsync($"{ServerBase}/health");
            ServerAvailable = resp.IsSuccessStatusCode;
        }
        catch
        {
            ServerAvailable = false;
        }
    }

    public Task DisposeAsync() => Task.CompletedTask;

    /// <summary>
    /// Call at the start of every test.  Skips via SkippableException when the
    /// server is unavailable so CI stays green even without a running server.
    /// </summary>
    public void RequireServer()
    {
        Skip.IfNot(ServerAvailable, "Agentspan server is not reachable — skipping e2e test.");
    }

    /// <summary>
    /// Fetch a workflow execution from the server API for runtime-state
    /// assertions. Mirrors Python's <c>_get_workflow(execution_id)</c> helper
    /// used in suites 6, 10, 12, 14 to inspect compiled task graphs after a
    /// <c>RunAsync</c> call.
    /// </summary>
    public async Task<JsonNode?> FetchWorkflowAsync(string executionId)
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var resp = await http.GetAsync($"{ServerBase}/api/workflow/{executionId}?includeTasks=true");
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadAsStringAsync();
        return JsonNode.Parse(body);
    }
}

[CollectionDefinition("E2e")]
public sealed class E2eCollection : ICollectionFixture<E2eFixture> { }
