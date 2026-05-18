// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Human-in-the-Loop with Custom Feedback.
//
// Demonstrates the general-purpose RespondAsync() API. Instead of a binary
// approve/reject, the human can send arbitrary feedback that the LLM processes
// on its next iteration. Uses interactive streaming with schema-driven console prompts.
//
// Use case: a content-publishing agent writes a blog post, and a human
// editor can approve, reject, or provide revision notes. The agent
// incorporates the feedback and tries again.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

var agent = new Agent("writer_09b")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new BlogTools()),
    Instructions =
        "You are a blog writer. When asked to write about a topic, draft an article " +
        "and publish it using the publish_article tool. If you receive editorial " +
        "feedback, revise the article and try publishing again.",
};

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Write a short blog post about the benefits of code review");
Console.WriteLine($"Started: {handle.ExecutionId}\n");

await foreach (var evt in handle.StreamAsync())
{
    switch (evt.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {evt.Content}");
            break;

        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {evt.ToolName}");
            break;

        case EventType.ToolResult:
            Console.WriteLine($"  [tool_result] {evt.ToolName}");
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

internal sealed class BlogTools
{
    [Tool("Publish an article to the blog. Requires editorial approval.",
          ApprovalRequired = true)]
    public Dictionary<string, object> PublishArticle(string title, string body)
        => new()
        {
            ["status"] = "published",
            ["title"]  = title,
            ["url"]    = $"/blog/{title.ToLowerInvariant().Replace(' ', '-')}",
        };
}
