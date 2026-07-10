// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Collections.Generic;
using System.Reflection;
using Xunit;
using ModelTask = Conductor.Client.Models.Task;

namespace Conductor.AI.Tests;

/// <summary>
/// Embedded host-delivery read-path: the worker reads host-resolved secret values from
/// <c>Task.RuntimeMetadata</c> (wire-only, resolved by the host from the worker's declared
/// <c>TaskDef.runtimeMetadata</c>; conductor-oss PR #1255). Absent/empty yields an empty map
/// (standalone falls back to the native token-pull).
/// </summary>
public class RuntimeMetadataReadTests
{
    private static Dictionary<string, string> Invoke(ModelTask task)
    {
        // WorkerPollLoop is internal; reach ReadRuntimeMetadata (private static) via reflection.
        var type = typeof(CredentialScope).Assembly.GetType("Conductor.AI.WorkerPollLoop")!;
        var method = type.GetMethod(
            "ReadRuntimeMetadata",
            BindingFlags.NonPublic | BindingFlags.Static)!;
        return (Dictionary<string, string>)method.Invoke(null, new object?[] { task })!;
    }

    [Fact]
    public void Extracts_host_delivered_values()
    {
        var task = new ModelTask(
            taskId: "t1",
            runtimeMetadata: new Dictionary<string, string>
            {
                ["GITHUB_TOKEN"] = "ghp_host",
                ["GH_APP_ID"] = "42",
            });

        var result = Invoke(task);

        Assert.Equal(2, result.Count);
        Assert.Equal("ghp_host", result["GITHUB_TOKEN"]);
        Assert.Equal("42", result["GH_APP_ID"]);
    }

    [Fact]
    public void Empty_when_absent_or_empty()
    {
        Assert.Empty(Invoke(new ModelTask(taskId: "t1")));
        Assert.Empty(Invoke(new ModelTask(
            taskId: "t1",
            runtimeMetadata: new Dictionary<string, string>())));
    }
}
