// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// SET 2 — LocalCodeExecutor mirroring Python's. Runs trivial snippets locally
/// (deterministic) and asserts the structured (never-throws) error paths.
/// </summary>
public class LocalCodeExecutorTests
{
    [Fact]
    public void Defaults_match_python()
    {
        var exec = new LocalCodeExecutor();
        Assert.Equal("python", exec.Language);
        Assert.Equal(30, exec.Timeout);
        Assert.Null(exec.WorkingDir);
    }

    [Fact]
    public async Task Python_prints_expected_output()
    {
        var exec = new LocalCodeExecutor(language: "python", timeout: 15);
        var result = await exec.ExecuteAsync("print(1+1)");
        Assert.True(result.Success);
        Assert.Equal("2", result.Output.Trim());
        Assert.Equal(0, result.ExitCode);
    }

    [Fact]
    public async Task Bash_echo_prints_expected_output()
    {
        var exec = new LocalCodeExecutor(language: "bash", timeout: 15);
        var result = await exec.ExecuteAsync("echo hello-bash");
        Assert.True(result.Success);
        Assert.Equal("hello-bash", result.Output.Trim());
    }

    [Fact]
    public async Task Empty_code_returns_success_noop()
    {
        var exec = new LocalCodeExecutor();
        var result = await exec.ExecuteAsync("");
        Assert.True(result.Success);
    }

    [Fact]
    public async Task Unsupported_language_returns_structured_error()
    {
        var exec = new LocalCodeExecutor(language: "cobol");
        var result = await exec.ExecuteAsync("DISPLAY 'x'.");
        Assert.False(result.Success);
        Assert.NotEqual(0, result.ExitCode);
        Assert.Contains("Unsupported language", result.Error);
    }

    [Fact]
    public async Task Nonzero_exit_is_reported_not_thrown()
    {
        var exec = new LocalCodeExecutor(language: "python", timeout: 15);
        // sys.exit(3) — process exits nonzero, executor must report it structurally.
        var result = await exec.ExecuteAsync("import sys; sys.exit(3)");
        Assert.False(result.Success);
        Assert.Equal(3, result.ExitCode);
    }
}
