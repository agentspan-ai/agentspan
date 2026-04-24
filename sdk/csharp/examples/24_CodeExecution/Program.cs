// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Code Execution — sandboxed Python code runner as an agent tool.
//
// LocalCodeExecutor runs Python code in a subprocess and returns stdout.
// The agent writes code, executes it, and shows results.
//
// Requirements:
//   - Agentspan server with LLM support
//   - Python 3.x installed locally
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Diagnostics;
using Agentspan;
using Agentspan.Examples;

// ── Local code executor tool ─────────────────────────────────────────

var executorTools = ToolRegistry.FromInstance(new LocalCodeExecutor(timeout: 10));

// ── Agent with code execution tool ──────────────────────────────────

var coder = new Agent("local_coder")
{
    Model        = Settings.LlmModel,
    Tools        = executorTools,
    Instructions =
        "You are a Python developer. Write and execute code to solve problems. " +
        "Always use the execute_code tool to run your code and show results.",
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Local Code Execution ---");
var result = await runtime.RunAsync(
    coder,
    "Write a Python function to find the first 10 Fibonacci numbers and print them.");

result.PrintResult();

// ── LocalCodeExecutor ─────────────────────────────────────────────────

/// <summary>Runs Python code in a local subprocess.</summary>
internal sealed class LocalCodeExecutor(int timeout = 10)
{
    [Tool("Execute Python code and return the output. Use this to run code and show results.")]
    public async Task<Dictionary<string, object>> ExecuteCode(string code, string language = "python")
    {
        var tmpFile = Path.Combine(Path.GetTempPath(), $"agentspan_{Guid.NewGuid():N}.py");
        try
        {
            await File.WriteAllTextAsync(tmpFile, code);

            using var proc = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName               = "python3",
                    Arguments              = tmpFile,
                    RedirectStandardOutput = true,
                    RedirectStandardError  = true,
                    UseShellExecute        = false,
                    CreateNoWindow         = true,
                },
            };

            proc.Start();
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeout));

            var stdout = await proc.StandardOutput.ReadToEndAsync(cts.Token);
            var stderr = await proc.StandardError.ReadToEndAsync(cts.Token);
            await proc.WaitForExitAsync(cts.Token);

            return new Dictionary<string, object>
            {
                ["stdout"]    = stdout.TrimEnd(),
                ["stderr"]    = stderr.TrimEnd(),
                ["exit_code"] = proc.ExitCode,
                ["language"]  = language,
            };
        }
        catch (OperationCanceledException)
        {
            return new Dictionary<string, object>
            {
                ["error"]    = $"Code execution timed out after {timeout}s",
                ["language"] = language,
            };
        }
        finally
        {
            try { File.Delete(tmpFile); } catch { /* best-effort */ }
        }
    }
}
