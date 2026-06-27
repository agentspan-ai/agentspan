// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Diagnostics;

namespace Conductor.AI;

// Reuses the existing <see cref="ExecutionResult"/> record defined in Result.cs
// (Output / Error / ExitCode / TimedOut / Success), matching Python's
// ExecutionResult shape.

/// <summary>
/// Execute code inside a Docker container, mirroring Python's
/// <c>DockerCodeExecutor</c>. Provides isolation — the code cannot access the
/// host filesystem or network unless explicitly configured.
///
/// <para>Requires Docker installed and the Docker daemon running.</para>
/// </summary>
public sealed class DockerCodeExecutor
{
    private readonly string _dockerPath;

    /// <param name="image">Docker image to use (default <c>python:3.12-slim</c>).</param>
    /// <param name="language">Programming language.</param>
    /// <param name="timeout">Max seconds before the container is killed.</param>
    /// <param name="networkEnabled">Whether the container has network access (default <c>false</c>).</param>
    /// <param name="memoryLimit">Container memory limit (e.g. <c>256m</c>).</param>
    /// <param name="volumes">Optional host:container volume mounts (mounted read-only).</param>
    /// <param name="dockerPath">Path/name of the docker binary (default <c>docker</c>). Overridable for testing.</param>
    public DockerCodeExecutor(
        string image = "python:3.12-slim",
        string language = "python",
        int timeout = 30,
        bool networkEnabled = false,
        string? memoryLimit = null,
        IReadOnlyDictionary<string, string>? volumes = null,
        string dockerPath = "docker")
    {
        Image          = image;
        Language       = language;
        Timeout        = timeout;
        NetworkEnabled = networkEnabled;
        MemoryLimit    = memoryLimit;
        Volumes        = volumes ?? new Dictionary<string, string>();
        _dockerPath    = dockerPath;
    }

    public string Image    { get; }
    public string Language { get; }
    public int    Timeout  { get; }
    public bool   NetworkEnabled { get; }
    public string? MemoryLimit   { get; }
    public IReadOnlyDictionary<string, string> Volumes { get; }

    /// <summary>Execute <paramref name="code"/> in a container and return the result. Never throws.</summary>
    public async Task<ExecutionResult> ExecuteAsync(string code, CancellationToken ct = default)
    {
        var args = new List<string> { "run", "--rm" };

        if (!NetworkEnabled) args.Add("--network=none");
        if (MemoryLimit is not null) { args.Add("--memory"); args.Add(MemoryLimit); }
        foreach (var (host, container) in Volumes) { args.Add("-v"); args.Add($"{host}:{container}:ro"); }

        var interpreter = Language switch
        {
            "python" => "python3",
            "bash"   => "bash",
            "node"   => "node",
            _        => "python3",
        };
        args.Add(Image);
        args.Add(interpreter);
        args.Add("-c");
        args.Add(code);

        var psi = new ProcessStartInfo(_dockerPath)
        {
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute        = false,
            CreateNoWindow         = true,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);

        Process? proc;
        try
        {
            proc = Process.Start(psi);
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return new ExecutionResult(
                Output: "",
                Error: "Docker not found. Install Docker to use DockerCodeExecutor.",
                ExitCode: 127);
        }
        catch (Exception ex)
        {
            return new ExecutionResult(Output: "", Error: ex.Message, ExitCode: 1);
        }

        if (proc is null)
            return new ExecutionResult(Output: "", Error: "Failed to start docker", ExitCode: 1);

        using (proc)
        {
            // Extra time for container startup, matching Python (timeout + 10).
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(Timeout + 10));

            var stdoutTask = proc.StandardOutput.ReadToEndAsync();
            var stderrTask = proc.StandardError.ReadToEndAsync();
            try
            {
                await proc.WaitForExitAsync(cts.Token);
                return new ExecutionResult(
                    Output: await stdoutTask,
                    Error: await stderrTask,
                    ExitCode: proc.ExitCode);
            }
            catch (OperationCanceledException)
            {
                try { proc.Kill(entireProcessTree: true); } catch { }
                return new ExecutionResult(
                    Output: "",
                    Error: $"Docker execution timed out after {Timeout}s",
                    ExitCode: -1,
                    TimedOut: true);
            }
        }
    }

    public override string ToString()
        => $"DockerCodeExecutor(image={Image}, language={Language}, timeout={Timeout})";
}
