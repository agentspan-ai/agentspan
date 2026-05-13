// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Human-in-the-Loop with Streaming — Console Interactive.
//
// Streams agent events in real time via SSE. When the agent pauses for
// human approval, the user is prompted in the console with schema-driven
// prompts and responds through the handle.
//
// Use case: an ops agent that can restart services (safe) and delete data
// (dangerous, requires approval). The operator watches the agent think
// in real time and intervenes only for destructive actions.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

var agent = new Agent("ops_agent_09c")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new OpsTools()),
    Instructions =
        "You are an operations assistant. You can check, restart, and manage services. " +
        "If a service is unhealthy, check it first, then restart it. Only suggest " +
        "deleting data if explicitly asked.",
};

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent,
    "The payments service is down. Check it, restart it, and clear its stale cache data.");
Console.WriteLine($"Started: {handle.ExecutionId}\n");

await foreach (var evt in handle.StreamAsync())
{
    switch (evt.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {evt.Content}");
            break;

        case EventType.ToolCall:
            var argsJson = evt.Args is not null ? JsonSerializer.Serialize(evt.Args) : "";
            Console.WriteLine($"  [tool_call] {evt.ToolName}({argsJson})");
            break;

        case EventType.ToolResult:
            var preview = evt.Result?.ToString();
            if (preview?.Length > 100) preview = preview[..100];
            Console.WriteLine($"  [tool_result] {evt.ToolName} -> {preview}");
            break;

        case EventType.Waiting:
            var status = await handle.GetStatusAsync();
            var pt = status.PendingTool ?? new();
            if (pt.TryGetValue("response_schema", out var schemaObj))
            {
                var schema = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
                    JsonSerializer.Serialize(schemaObj));
                var props = schema?.TryGetValue("properties", out var p) == true
                    ? JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(p.GetRawText())
                    : null;

                Console.WriteLine("\n--- Human input required ---");
                var response = new Dictionary<string, object>();
                if (props is not null)
                {
                    foreach (var (field, fs) in props)
                    {
                        var fieldSchema = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(fs.GetRawText());
                        var desc = fieldSchema?.TryGetValue("description", out var d) == true ? d.GetString()
                               : fieldSchema?.TryGetValue("title", out var t) == true ? t.GetString()
                               : field;
                        var type = fieldSchema?.TryGetValue("type", out var tp) == true ? tp.GetString() : "string";

                        if (type == "boolean")
                        {
                            Console.Write($"  {desc} (y/n): ");
                            var val = Console.ReadLine()?.Trim().ToLower() ?? "";
                            response[field] = val is "y" or "yes";
                        }
                        else
                        {
                            Console.Write($"  {desc}: ");
                            response[field] = Console.ReadLine() ?? "";
                        }
                    }
                }
                await handle.RespondAsync(response);
                Console.WriteLine();
            }
            break;

        case EventType.Done:
            Console.WriteLine($"\nDone: {evt.Content}");
            break;
    }
}

// ── Tool class ─────────────────────────────────────────────────

internal sealed class OpsTools
{
    [Tool("Check the health of a service.")]
    public Dictionary<string, object> CheckService(string serviceName)
        => new() { ["service"] = serviceName, ["status"] = "unhealthy", ["uptime"] = "0m" };

    [Tool("Restart a service. Safe operation, no approval needed.")]
    public Dictionary<string, object> RestartService(string serviceName)
        => new() { ["service"] = serviceName, ["status"] = "restarted", ["new_uptime"] = "0m" };

    [Tool("Delete service data. Destructive — requires human approval.", ApprovalRequired = true)]
    public Dictionary<string, object> DeleteServiceData(string serviceName, string dataType)
        => new() { ["service"] = serviceName, ["data_type"] = dataType, ["status"] = "deleted" };
}
