// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Fix #4 — tier-1 credential accessor. The worker populates an AsyncLocal
/// credential scope immediately before invoking a tool; ToolContext.GetCredential
/// (and Secrets.Get) read it. Mirrors Java ToolContext.getCredential /
/// TS getCredential.
/// </summary>
public class CredentialAccessorTests
{
    [Fact]
    public async Task GetCredential_reads_scoped_value()
    {
        var creds = new Dictionary<string, string> { ["STRIPE_KEY"] = "sk_123" };
        using (CredentialScope.Begin(creds))
        {
            Assert.Equal("sk_123", ToolContext.GetCredential("STRIPE_KEY"));
            Assert.Equal("sk_123", Secrets.Get("STRIPE_KEY"));
        }
        await Task.CompletedTask;
    }

    [Fact]
    public void GetCredential_outside_scope_returns_null()
    {
        Assert.Null(ToolContext.GetCredential("ANYTHING"));
    }

    [Fact]
    public void GetCredential_unknown_name_returns_null_inside_scope()
    {
        var creds = new Dictionary<string, string> { ["A"] = "1" };
        using (CredentialScope.Begin(creds))
        {
            Assert.Null(ToolContext.GetCredential("B"));
        }
    }

    [Fact]
    public void Scope_is_async_local_and_restores_on_dispose()
    {
        var creds = new Dictionary<string, string> { ["K"] = "v" };
        var scope = CredentialScope.Begin(creds);
        Assert.Equal("v", ToolContext.GetCredential("K"));
        scope.Dispose();
        Assert.Null(ToolContext.GetCredential("K"));
    }

    [Fact]
    public async Task Scopes_do_not_leak_across_concurrent_async_flows()
    {
        async Task<string?> Run(string name, string val)
        {
            using (CredentialScope.Begin(new Dictionary<string, string> { [name] = val }))
            {
                await Task.Yield();
                return ToolContext.GetCredential(name);
            }
        }

        var a = Run("A", "1");
        var b = Run("B", "2");
        var results = await Task.WhenAll(a, b);
        Assert.Equal("1", results[0]);
        Assert.Equal("2", results[1]);
    }
}
