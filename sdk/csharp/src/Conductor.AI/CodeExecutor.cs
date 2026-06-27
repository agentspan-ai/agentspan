// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Diagnostics;
using System.Net.Http;
using System.Net.Http.Json;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

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

/// <summary>
/// Execute code in a local subprocess, mirroring Python's <c>LocalCodeExecutor</c>.
///
/// <para><b>Warning:</b> no sandboxing — the code runs with the same permissions
/// as the host process. Use <see cref="DockerCodeExecutor"/> for untrusted code.</para>
/// </summary>
public sealed class LocalCodeExecutor
{
    // Map language → interpreter argv[0]. Mirrors Python's _INTERPRETERS table.
    private static readonly IReadOnlyDictionary<string, string> Interpreters =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["python"]     = "python3",
            ["python3"]    = "python3",
            ["bash"]       = "bash",
            ["sh"]         = "sh",
            ["node"]       = "node",
            ["javascript"] = "node",
            ["ruby"]       = "ruby",
        };

    private static readonly IReadOnlyDictionary<string, string> Extensions =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["python"]     = ".py",
            ["python3"]    = ".py",
            ["bash"]       = ".sh",
            ["sh"]         = ".sh",
            ["node"]       = ".js",
            ["javascript"] = ".js",
            ["ruby"]       = ".rb",
        };

    /// <param name="language">Programming language (<c>python</c>, <c>bash</c>, <c>node</c>, <c>ruby</c>, …).</param>
    /// <param name="timeout">Max seconds before the process is killed.</param>
    /// <param name="workingDir">Working directory for execution.</param>
    public LocalCodeExecutor(string language = "python", int timeout = 30, string? workingDir = null)
    {
        Language   = language;
        Timeout    = timeout;
        WorkingDir = workingDir;
    }

    public string  Language   { get; }
    public int     Timeout    { get; }
    public string? WorkingDir { get; }

    /// <summary>Execute <paramref name="code"/> in a subprocess and return the result. Never throws.</summary>
    public async Task<ExecutionResult> ExecuteAsync(string code, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(code))
            return new ExecutionResult(Output: "No code provided. Nothing to execute.", ExitCode: 0);

        if (!Interpreters.TryGetValue(Language, out var interpreter))
            return new ExecutionResult(Output: "", Error: $"Unsupported language: {Language}", ExitCode: 1);

        var ext = Extensions.TryGetValue(Language, out var e) ? e : ".txt";
        var tmpPath = Path.Combine(Path.GetTempPath(), $"conductor_code_{Guid.NewGuid():N}{ext}");

        try
        {
            await File.WriteAllTextAsync(tmpPath, code, ct);

            var psi = new ProcessStartInfo(interpreter)
            {
                RedirectStandardOutput = true,
                RedirectStandardError  = true,
                UseShellExecute        = false,
                CreateNoWindow         = true,
            };
            psi.ArgumentList.Add(tmpPath);
            if (WorkingDir is not null) psi.WorkingDirectory = WorkingDir;

            Process? proc;
            try
            {
                proc = Process.Start(psi);
            }
            catch (System.ComponentModel.Win32Exception)
            {
                return new ExecutionResult(Output: "", Error: $"Interpreter not found: {interpreter}", ExitCode: 127);
            }
            if (proc is null)
                return new ExecutionResult(Output: "", Error: $"Failed to start {interpreter}", ExitCode: 1);

            using (proc)
            {
                using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                cts.CancelAfter(TimeSpan.FromSeconds(Timeout));

                var stdoutTask = proc.StandardOutput.ReadToEndAsync();
                var stderrTask = proc.StandardError.ReadToEndAsync();
                try
                {
                    await proc.WaitForExitAsync(cts.Token);
                    return new ExecutionResult(
                        Output:   await stdoutTask,
                        Error:    await stderrTask,
                        ExitCode: proc.ExitCode);
                }
                catch (OperationCanceledException)
                {
                    try { proc.Kill(entireProcessTree: true); } catch { }
                    return new ExecutionResult(
                        Output: "",
                        Error: $"Execution timed out after {Timeout}s",
                        ExitCode: -1,
                        TimedOut: true);
                }
            }
        }
        catch (Exception ex)
        {
            return new ExecutionResult(Output: "", Error: ex.Message, ExitCode: 1);
        }
        finally
        {
            try { File.Delete(tmpPath); } catch { /* best-effort cleanup */ }
        }
    }

    public override string ToString()
        => $"LocalCodeExecutor(language={Language}, timeout={Timeout})";
}

/// <summary>
/// Execute code via a Jupyter Kernel Gateway, mirroring Python's
/// <c>JupyterCodeExecutor</c>. Kernel state persists across executions (variables
/// and imports survive between calls), just like a notebook.
///
/// <para>Talks to a running Jupyter Kernel Gateway over its REST + WebSocket API:
/// a kernel is created via <c>POST {url}/api/kernels</c> and code is executed over
/// the kernel's WebSocket channel. Requires a reachable gateway — when none is
/// available the executor returns a structured (non-throwing) error result.</para>
/// </summary>
public sealed class JupyterCodeExecutor : IAsyncDisposable
{
    private readonly HttpClient _http;
    private ClientWebSocket? _ws;
    private string? _kernelId;
    private bool _startupRun;

    /// <param name="url">Base URL of the Jupyter Kernel Gateway (e.g. <c>http://localhost:8888</c>).</param>
    /// <param name="kernelName">Jupyter kernel name (default <c>python3</c>).</param>
    /// <param name="timeout">Max seconds per cell execution.</param>
    /// <param name="token">Optional gateway auth token.</param>
    /// <param name="startupCode">Optional code run once when the kernel starts.</param>
    public JupyterCodeExecutor(
        string  url        = "http://localhost:8888",
        string  kernelName = "python3",
        int     timeout    = 30,
        string? token      = null,
        string? startupCode = null)
    {
        Url         = url.TrimEnd('/');
        KernelName  = kernelName;
        Timeout     = timeout;
        Token       = token;
        StartupCode = startupCode;
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(timeout + 5) };
        if (token is not null)
            _http.DefaultRequestHeaders.Add("Authorization", $"token {token}");
    }

    public string  Url         { get; }
    public string  KernelName  { get; }
    public int     Timeout     { get; }
    public string? Token       { get; }
    public string? StartupCode { get; }

    /// <summary>Execute <paramref name="code"/> in the kernel and return the result. Never throws.</summary>
    public async Task<ExecutionResult> ExecuteAsync(string code, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(code))
            return new ExecutionResult(Output: "No code provided. Nothing to execute.", ExitCode: 0);

        try
        {
            await EnsureKernelAsync(ct);
        }
        catch (Exception ex)
        {
            return new ExecutionResult(Output: "", Error: $"Kernel startup failed: {ex.Message}", ExitCode: 1);
        }

        try
        {
            if (StartupCode is not null && !_startupRun)
            {
                _startupRun = true;
                await RunCellAsync(StartupCode, ct);
            }
            return await RunCellAsync(code, ct);
        }
        catch (OperationCanceledException)
        {
            return new ExecutionResult(
                Output: "", Error: $"Execution timed out after {Timeout}s", ExitCode: -1, TimedOut: true);
        }
        catch (Exception ex)
        {
            return new ExecutionResult(Output: "", Error: ex.Message, ExitCode: 1);
        }
    }

    private async Task EnsureKernelAsync(CancellationToken ct)
    {
        if (_ws is { State: WebSocketState.Open }) return;

        var resp = await _http.PostAsJsonAsync($"{Url}/api/kernels",
            new { name = KernelName }, ct);
        resp.EnsureSuccessStatusCode();
        var node = JsonNode.Parse(await resp.Content.ReadAsStringAsync(ct));
        _kernelId = node?["id"]?.GetValue<string>()
            ?? throw new InvalidOperationException("Gateway did not return a kernel id");

        var wsScheme = Url.StartsWith("https", StringComparison.OrdinalIgnoreCase) ? "wss" : "ws";
        var baseUri = new Uri(Url);
        var wsUri = new UriBuilder(baseUri)
        {
            Scheme = wsScheme,
            Path   = $"/api/kernels/{_kernelId}/channels",
        }.Uri;

        _ws = new ClientWebSocket();
        if (Token is not null) _ws.Options.SetRequestHeader("Authorization", $"token {Token}");
        await _ws.ConnectAsync(wsUri, ct);
    }

    private async Task<ExecutionResult> RunCellAsync(string code, CancellationToken ct)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(Timeout));

        var msgId = Guid.NewGuid().ToString("N");
        var request = new JsonObject
        {
            ["header"] = new JsonObject
            {
                ["msg_id"]   = msgId,
                ["username"] = "conductor",
                ["session"]  = Guid.NewGuid().ToString("N"),
                ["msg_type"] = "execute_request",
                ["version"]  = "5.3",
            },
            ["parent_header"] = new JsonObject(),
            ["metadata"]      = new JsonObject(),
            ["content"] = new JsonObject
            {
                ["code"]             = code,
                ["silent"]           = false,
                ["store_history"]    = true,
                ["allow_stdin"]      = false,
                ["stop_on_error"]    = true,
            },
            ["channel"] = "shell",
        };

        var bytes = Encoding.UTF8.GetBytes(request.ToJsonString());
        await _ws!.SendAsync(bytes, WebSocketMessageType.Text, endOfMessage: true, cts.Token);

        var outputs = new StringBuilder();
        var errors  = new StringBuilder();
        var buffer  = new byte[64 * 1024];

        while (true)
        {
            using var ms = new MemoryStream();
            WebSocketReceiveResult recv;
            do
            {
                recv = await _ws.ReceiveAsync(buffer, cts.Token);
                if (recv.MessageType == WebSocketMessageType.Close)
                    return new ExecutionResult(Output: outputs.ToString(), Error: errors.ToString(),
                        ExitCode: errors.Length > 0 ? 1 : 0);
                ms.Write(buffer, 0, recv.Count);
            } while (!recv.EndOfMessage);

            var msg = JsonNode.Parse(Encoding.UTF8.GetString(ms.ToArray()));
            var parentId = msg?["parent_header"]?["msg_id"]?.GetValue<string>();
            if (parentId != msgId) continue;  // ignore unrelated traffic

            var msgType = msg?["header"]?["msg_type"]?.GetValue<string>() ?? "";
            var content = msg?["content"];

            switch (msgType)
            {
                case "stream":
                    var text = content?["text"]?.GetValue<string>() ?? "";
                    if (content?["name"]?.GetValue<string>() == "stderr") errors.Append(text);
                    else outputs.Append(text);
                    break;
                case "execute_result":
                case "display_data":
                    outputs.Append(content?["data"]?["text/plain"]?.GetValue<string>() ?? "");
                    break;
                case "error":
                    if (content?["traceback"] is JsonArray tb)
                        errors.Append(string.Join("\n", tb.Select(n => n?.GetValue<string>() ?? "")));
                    break;
                case "status":
                    if (content?["execution_state"]?.GetValue<string>() == "idle")
                        return new ExecutionResult(
                            Output: outputs.ToString(),
                            Error:  errors.ToString(),
                            ExitCode: errors.Length > 0 ? 1 : 0);
                    break;
            }
        }
    }

    /// <summary>Shut down the kernel and release resources.</summary>
    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_ws is not null)
            {
                if (_ws.State == WebSocketState.Open)
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
                _ws.Dispose();
            }
            if (_kernelId is not null)
                await _http.DeleteAsync($"{Url}/api/kernels/{_kernelId}");
        }
        catch { /* best-effort shutdown */ }
        finally { _http.Dispose(); }
    }

    public override string ToString()
        => $"JupyterCodeExecutor(url={Url}, kernel={KernelName}, timeout={Timeout})";
}

/// <summary>
/// Execute code via a remote serverless execution service, mirroring Python's
/// <c>ServerlessCodeExecutor</c>. POSTs a JSON body
/// <c>{code, language, timeout}</c> to the configured endpoint and reads
/// <c>{output|stdout, error|stderr, exit_code}</c> back. Never throws — returns a
/// structured error result when the endpoint is unavailable.
/// </summary>
public sealed class ServerlessCodeExecutor
{
    private readonly HttpClient _http;

    /// <param name="endpoint">HTTP endpoint URL of the execution service.</param>
    /// <param name="apiKey">Optional API key sent as <c>Authorization: Bearer …</c>.</param>
    /// <param name="language">Programming language.</param>
    /// <param name="timeout">Max seconds to wait for a response.</param>
    /// <param name="headers">Optional additional HTTP headers.</param>
    public ServerlessCodeExecutor(
        string  endpoint,
        string? apiKey   = null,
        string  language = "python",
        int     timeout  = 30,
        IReadOnlyDictionary<string, string>? headers = null)
    {
        Endpoint = endpoint;
        ApiKey   = apiKey;
        Language = language;
        Timeout  = timeout;
        Headers  = headers ?? new Dictionary<string, string>();
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(timeout + 5) };
    }

    public string  Endpoint { get; }
    public string? ApiKey   { get; }
    public string  Language { get; }
    public int     Timeout  { get; }
    public IReadOnlyDictionary<string, string> Headers { get; }

    /// <summary>POST <paramref name="code"/> to the endpoint and return the result. Never throws.</summary>
    public async Task<ExecutionResult> ExecuteAsync(string code, CancellationToken ct = default)
    {
        try
        {
            var payload = new JsonObject
            {
                ["code"]     = code,
                ["language"] = Language,
                ["timeout"]  = Timeout,
            };

            using var req = new HttpRequestMessage(HttpMethod.Post, Endpoint)
            {
                Content = new StringContent(payload.ToJsonString(), Encoding.UTF8, "application/json"),
            };
            foreach (var (k, v) in Headers) req.Headers.TryAddWithoutValidation(k, v);
            if (ApiKey is not null)
                req.Headers.TryAddWithoutValidation("Authorization", $"Bearer {ApiKey}");

            using var resp = await _http.SendAsync(req, ct);
            var body = await resp.Content.ReadAsStringAsync(ct);
            if (!resp.IsSuccessStatusCode)
                return new ExecutionResult(Output: "",
                    Error: $"Request failed: {(int)resp.StatusCode} {resp.ReasonPhrase}", ExitCode: 1);

            var node = JsonNode.Parse(body)?.AsObject();
            string Get(string a, string b) =>
                node?[a]?.GetValue<string>() ?? node?[b]?.GetValue<string>() ?? "";
            var exit = 0;
            if (node?["exit_code"] is JsonNode ec)
                try { exit = ec.GetValue<int>(); } catch { int.TryParse(ec.ToString(), out exit); }

            return new ExecutionResult(
                Output:   Get("output", "stdout"),
                Error:    Get("error", "stderr"),
                ExitCode: exit);
        }
        catch (Exception ex)
        {
            return new ExecutionResult(Output: "", Error: $"Request failed: {ex.Message}", ExitCode: 1);
        }
    }

    public override string ToString()
        => $"ServerlessCodeExecutor(endpoint={Endpoint}, language={Language})";
}
