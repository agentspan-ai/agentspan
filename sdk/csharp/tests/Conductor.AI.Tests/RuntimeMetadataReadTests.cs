// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Collections.Generic;
using System.Reflection;
using Xunit;
using ModelTask = Conductor.Client.Models.Task;

namespace Conductor.AI.Tests;

/// <summary>
/// The ONLY credential-delivery read-path: the worker reads host-resolved secret values from
/// <c>Task.RuntimeMetadata</c> (wire-only, resolved by the conductor core at poll from the
/// worker's declared <c>TaskDef.runtimeMetadata</c>; conductor-oss PR #1255). There is no server
/// endpoint to pull from.
///
/// <para>The read is reflective because the published conductor-csharp <c>Task</c> does not carry
/// the property yet: against today's client it returns an empty map (covered below), and it
/// lights up automatically once the client ships <c>Task.RuntimeMetadata</c> — simulated here
/// with a <c>Task</c> subclass exposing the property.</para>
/// </summary>
public class RuntimeMetadataReadTests
{
    /// <summary>Simulates a conductor-csharp Task model that carries the RuntimeMetadata field.</summary>
    private sealed class TaskWithRuntimeMetadata : ModelTask
    {
        public Dictionary<string, string>? RuntimeMetadata { get; set; }
    }

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
        var task = new TaskWithRuntimeMetadata
        {
            RuntimeMetadata = new Dictionary<string, string>
            {
                ["GITHUB_TOKEN"] = "ghp_host",
                ["GH_APP_ID"] = "42",
            },
        };

        var result = Invoke(task);

        Assert.Equal(2, result.Count);
        Assert.Equal("ghp_host", result["GITHUB_TOKEN"]);
        Assert.Equal("42", result["GH_APP_ID"]);
    }

    [Fact]
    public void Empty_when_absent_or_empty()
    {
        Assert.Empty(Invoke(new TaskWithRuntimeMetadata()));
        Assert.Empty(Invoke(new TaskWithRuntimeMetadata
        {
            RuntimeMetadata = new Dictionary<string, string>(),
        }));
    }

    [Fact]
    public void Empty_against_published_client_without_the_field()
    {
        // The published conductor-csharp Task has no RuntimeMetadata property: the
        // reflective read must degrade to an empty map, not throw.
        Assert.Empty(Invoke(new ModelTask()));
    }
}
