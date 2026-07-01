// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// SET 2 — Jupyter and Serverless code executors. We do NOT require a live
/// kernel or endpoint; we assert the config surface and the structured
/// (non-throwing) error path when the kernel/endpoint is unavailable, mirroring
/// the DockerCodeExecutor missing-binary test.
/// </summary>
public class JupyterCodeExecutorTests
{
    [Fact]
    public void Defaults_match_python()
    {
        var exec = new JupyterCodeExecutor();
        Assert.Equal("python3", exec.KernelName);
        Assert.Equal(30, exec.Timeout);
        Assert.Null(exec.StartupCode);
    }

    [Fact]
    public void Config_surface_is_settable()
    {
        var exec = new JupyterCodeExecutor(
            url: "http://localhost:8888",
            kernelName: "python3",
            timeout: 10,
            token: "abc",
            startupCode: "import math");
        Assert.Equal("http://localhost:8888", exec.Url);
        Assert.Equal(10, exec.Timeout);
        Assert.Equal("abc", exec.Token);
        Assert.Equal("import math", exec.StartupCode);
    }

    [Fact]
    public async Task Unavailable_gateway_returns_structured_result_never_throws()
    {
        // Point at a closed port so the connection fails fast. Must return a
        // structured ExecutionResult, not throw.
        var exec = new JupyterCodeExecutor(url: "http://127.0.0.1:1", timeout: 2);
        var result = await exec.ExecuteAsync("print('hi')");
        Assert.False(result.Success);
        Assert.NotEqual(0, result.ExitCode);
    }
}

public class ServerlessCodeExecutorTests
{
    [Fact]
    public void Defaults_match_python()
    {
        var exec = new ServerlessCodeExecutor(endpoint: "https://api.example.com/run");
        Assert.Equal("https://api.example.com/run", exec.Endpoint);
        Assert.Equal("python", exec.Language);
        Assert.Equal(30, exec.Timeout);
        Assert.Null(exec.ApiKey);
        Assert.Empty(exec.Headers);
    }

    [Fact]
    public void Config_surface_is_settable()
    {
        var exec = new ServerlessCodeExecutor(
            endpoint: "https://api.example.com/run",
            apiKey: "sk-123",
            language: "node",
            timeout: 12,
            headers: new Dictionary<string, string> { ["X-Trace"] = "1" });
        Assert.Equal("node", exec.Language);
        Assert.Equal(12, exec.Timeout);
        Assert.Equal("sk-123", exec.ApiKey);
        Assert.Equal("1", exec.Headers["X-Trace"]);
    }

    [Fact]
    public async Task Unavailable_endpoint_returns_structured_result_never_throws()
    {
        // Closed port → connection refused. Must return a structured result.
        var exec = new ServerlessCodeExecutor(endpoint: "http://127.0.0.1:1/run", timeout: 2);
        var result = await exec.ExecuteAsync("print('hi')");
        Assert.False(result.Success);
        Assert.NotEqual(0, result.ExitCode);
    }
}
