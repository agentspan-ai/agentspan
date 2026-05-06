// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Agentspan;

/// <summary>
/// Factory for creating agents backed by the OpenAI Assistants API.
///
/// Each call to the returned agent's internal tool creates a Thread,
/// posts the message, polls the Run to completion, and returns the
/// assistant's reply — all via the OpenAI beta Assistants API.
/// </summary>
public static class GPTAssistantAgent
{
    /// <summary>Create an agent that uses an existing OpenAI Assistant.</summary>
    /// <param name="name">Agent name.</param>
    /// <param name="assistantId">An existing OpenAI Assistant ID (e.g. <c>asst_abc123</c>).</param>
    /// <param name="model">LLM model for the outer Agentspan agent.</param>
    /// <param name="apiKey">OpenAI API key (falls back to <c>OPENAI_API_KEY</c> env var).</param>
    public static Agent FromExistingAssistant(
        string  name,
        string  assistantId,
        string? model  = null,
        string? apiKey = null)
    {
        var runner = new AssistantRunner(existingAssistantId: assistantId, apiKey: apiKey);
        return BuildAgent(name, model, null, runner);
    }

    /// <summary>Create a new OpenAI Assistant on the fly and wrap it as an Agentspan agent.</summary>
    /// <param name="name">Agent name.</param>
    /// <param name="model">OpenAI model (e.g. <c>"openai/gpt-4o-mini"</c>).</param>
    /// <param name="instructions">System instructions for the assistant.</param>
    /// <param name="openAiTools">OpenAI-native tool specs, e.g. <c>[{"type":"code_interpreter"}]</c>.</param>
    /// <param name="apiKey">OpenAI API key (falls back to <c>OPENAI_API_KEY</c> env var).</param>
    public static Agent Create(
        string                                      name,
        string?                                     model        = null,
        string?                                     instructions = null,
        IEnumerable<Dictionary<string, object>>?    openAiTools  = null,
        string?                                     apiKey       = null)
    {
        // Strip provider prefix from model if present
        var rawModel = model is not null && model.Contains('/')
            ? model.Split('/')[1]
            : model ?? "gpt-4o-mini";

        var runner = new AssistantRunner(
            model:        rawModel,
            instructions: instructions,
            openAiTools:  openAiTools?.ToList(),
            apiKey:       apiKey);

        return BuildAgent(name, model, instructions, runner);
    }

    private static Agent BuildAgent(string name, string? model, string? instructions, AssistantRunner runner)
    {
        var toolName = $"{name}_assistant_call";
        var schema   = new JsonObject
        {
            ["type"] = "object",
            ["properties"] = new JsonObject
            {
                ["message"] = new JsonObject { ["type"] = "string" },
            },
            ["required"] = new JsonArray { "message" },
        };

        var toolDef = new ToolDef
        {
            Name        = toolName,
            Description = "Send a message to the OpenAI Assistant and get a response.",
            InputSchema = schema,
            Handler     = async (args, _) =>
            {
                var message = args.TryGetValue("message", out var m)
                    ? m.GetString() ?? ""
                    : "";
                return (object?)await runner.CallAsync(message);
            },
        };

        return new Agent(name)
        {
            Model        = model ?? "openai/gpt-4o-mini",
            Instructions = instructions ?? "You are a helpful assistant.",
            Tools        = [toolDef],
        };
    }
}

// ── Internal Assistants API runner ────────────────────────────────────────

internal sealed class AssistantRunner
{
    private readonly string?                            _existingAssistantId;
    private readonly string?                            _model;
    private readonly string?                            _instructions;
    private readonly List<Dictionary<string, object>>?  _openAiTools;
    private readonly string?                            _apiKey;
    private string?                                     _assistantId;

    private static readonly HttpClient _client = new();

    public AssistantRunner(
        string? existingAssistantId = null,
        string? model               = null,
        string? instructions        = null,
        List<Dictionary<string, object>>? openAiTools = null,
        string? apiKey              = null)
    {
        _existingAssistantId = existingAssistantId;
        _model               = model;
        _instructions        = instructions;
        _openAiTools         = openAiTools;
        _apiKey              = apiKey;
    }

    public async Task<string> CallAsync(string message)
    {
        var apiKey = _apiKey ?? Environment.GetEnvironmentVariable("OPENAI_API_KEY");
        if (string.IsNullOrEmpty(apiKey))
            return "Error: No OpenAI API key provided (set OPENAI_API_KEY).";

        try
        {
            var assistantId = _existingAssistantId ?? await EnsureAssistantAsync(apiKey);

            // Create thread
            var thread = await PostAsync("/v1/threads", null, apiKey);
            var threadId = thread?["id"]?.GetValue<string>()
                ?? throw new InvalidOperationException("No thread ID returned.");

            // Post message
            await PostAsync($"/v1/threads/{threadId}/messages",
                new { role = "user", content = message }, apiKey);

            // Start run
            var run = await PostAsync($"/v1/threads/{threadId}/runs",
                new { assistant_id = assistantId }, apiKey);
            var runId = run?["id"]?.GetValue<string>()
                ?? throw new InvalidOperationException("No run ID returned.");

            // Poll until complete
            string runStatus;
            do
            {
                await Task.Delay(1000);
                var status = await GetAsync($"/v1/threads/{threadId}/runs/{runId}", apiKey);
                runStatus = status?["status"]?.GetValue<string>() ?? "failed";
            }
            while (runStatus is "queued" or "in_progress");

            if (runStatus != "completed")
                return $"Assistant run ended with status: {runStatus}";

            // Get messages
            var messages = await GetAsync($"/v1/threads/{threadId}/messages", apiKey);
            var data = messages?["data"]?.AsArray();
            if (data is null) return "No messages returned.";

            foreach (var msg in data)
            {
                if (msg?["role"]?.GetValue<string>() != "assistant") continue;
                var content = msg["content"]?.AsArray();
                if (content is null) continue;

                var parts = new List<string>();
                foreach (var block in content)
                {
                    var text = block?["text"]?["value"]?.GetValue<string>();
                    if (text is not null) parts.Add(text);
                }
                if (parts.Count > 0) return string.Join("\n", parts);
            }
            return "No response from assistant.";
        }
        catch (Exception ex)
        {
            return $"OpenAI Assistant error: {ex.Message}";
        }
    }

    private async Task<string> EnsureAssistantAsync(string apiKey)
    {
        if (_assistantId is not null) return _assistantId;

        var body = new Dictionary<string, object>
        {
            ["model"] = _model ?? "gpt-4o-mini",
        };
        if (_instructions is not null) body["instructions"] = _instructions;
        if (_openAiTools?.Count > 0)   body["tools"]        = _openAiTools;

        var result = await PostAsync("/v1/assistants", body, apiKey);
        _assistantId = result?["id"]?.GetValue<string>()
            ?? throw new InvalidOperationException("No assistant ID returned.");
        return _assistantId;
    }

    private static async Task<JsonNode?> PostAsync(string path, object? body, string apiKey)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"https://api.openai.com{path}");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        request.Headers.Add("OpenAI-Beta", "assistants=v2");
        if (body is not null)
        {
            var json = JsonSerializer.Serialize(body);
            request.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }
        var response = await _client.SendAsync(request);
        var responseBody = await response.Content.ReadAsStringAsync();
        return JsonNode.Parse(responseBody);
    }

    private static async Task<JsonNode?> GetAsync(string path, string apiKey)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, $"https://api.openai.com{path}");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        request.Headers.Add("OpenAI-Beta", "assistants=v2");
        var response = await _client.SendAsync(request);
        var responseBody = await response.Content.ReadAsStringAsync();
        return JsonNode.Parse(responseBody);
    }
}
