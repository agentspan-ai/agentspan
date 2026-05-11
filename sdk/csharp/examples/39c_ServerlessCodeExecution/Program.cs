// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Serverless Code Execution — run code via a remote HTTP API.
//
// The ServerlessExecutor tool sends code to an HTTP endpoint and returns
// the result. Use this to offload execution to a hosted sandbox, AWS Lambda,
// Google Cloud Functions, or any service that accepts a JSON payload:
//
//   POST /execute
//   { "code": "print('hello')", "language": "python", "timeout": 30 }
//
//   Response:
//   { "output": "hello\n", "error": "", "exit_code": 0 }
//
// This example starts a tiny local HTTP server to simulate the remote service,
// then runs an agent that executes code through it.
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;

// ── Tiny mock execution server ────────────────────────────────────────
// Handles POST /execute by running code in a subprocess.

const int MockPort = 9753;

var listener = new HttpListener();
listener.Prefixes.Add($"http://127.0.0.1:{MockPort}/");
listener.Start();

var serverTask = Task.Run(async () =>
{
    while (listener.IsListening)
    {
        HttpListenerContext ctx;
        try { ctx = await listener.GetContextAsync(); }
        catch { break; }

        _ = Task.Run(async () =>
        {
            using var body   = ctx.Request.InputStream;
            using var reader = new System.IO.StreamReader(body);
            var json    = await reader.ReadToEndAsync();
            var req     = JsonNode.Parse(json);
            var code    = req?["code"]?.GetValue<string>() ?? "";
            var timeout = req?["timeout"]?.GetValue<int>() ?? 10;

            JsonObject resp;
            try
            {
                using var proc = new Process();
                proc.StartInfo = new ProcessStartInfo
                {
                    FileName               = "python3",
                    UseShellExecute        = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError  = true,
                };
                proc.StartInfo.ArgumentList.Add("-c");
                proc.StartInfo.ArgumentList.Add(code);
                proc.Start();

                using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeout));
                var stdout = await proc.StandardOutput.ReadToEndAsync(cts.Token);
                var stderr = await proc.StandardError.ReadToEndAsync(cts.Token);
                await proc.WaitForExitAsync(cts.Token);

                resp = new JsonObject
                {
                    ["output"]    = stdout,
                    ["error"]     = stderr,
                    ["exit_code"] = proc.ExitCode,
                };
            }
            catch (OperationCanceledException)
            {
                resp = new JsonObject
                {
                    ["output"] = "", ["error"] = "Timed out", ["exit_code"] = 1,
                };
            }

            var bytes = Encoding.UTF8.GetBytes(resp.ToJsonString());
            ctx.Response.ContentType = "application/json";
            ctx.Response.ContentLength64 = bytes.Length;
            await ctx.Response.OutputStream.WriteAsync(bytes);
            ctx.Response.Close();
        });
    }
});

// ── Agent setup ───────────────────────────────────────────────────────

var executorTool = ToolRegistry.FromInstance(
    new ServerlessExecutor($"http://127.0.0.1:{MockPort}/execute"));

var agent = new Agent("serverless_coder_39c")
{
    Model        = Settings.LlmModel,
    Tools        = executorTool,
    Instructions =
        "You write Python code that runs on a remote execution service. " +
        "Use the execute_code tool to run code remotely.",
};

// ── Run ───────────────────────────────────────────────────────────────

Console.WriteLine("--- Serverless Code Execution ---");
Console.WriteLine($"Mock execution server listening on port {MockPort}...\n");

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Calculate 2**100 and print the result.");
result.PrintResult();

listener.Stop();

// ── Serverless executor tool ──────────────────────────────────────────

internal sealed class ServerlessExecutor(string endpoint)
{
    private static readonly HttpClient _http = new();

    [Tool("Execute Python code on a remote execution service. Returns stdout/stderr.")]
    public async Task<string> ExecuteCode(string code, int timeoutSeconds = 15)
    {
        var payload = JsonSerializer.Serialize(new
        {
            code,
            language = "python",
            timeout  = timeoutSeconds,
        });

        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        using var resp    = await _http.PostAsync(endpoint, content);
        var body = await resp.Content.ReadAsStringAsync();

        var result   = JsonNode.Parse(body);
        var output   = result?["output"]?.GetValue<string>() ?? "";
        var error    = result?["error"]?.GetValue<string>() ?? "";
        var exitCode = result?["exit_code"]?.GetValue<int>() ?? -1;

        return exitCode == 0 ? output.Trim() : $"Error (exit {exitCode}): {error.Trim()}";
    }
}
