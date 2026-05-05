// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Agentspan;

// ── GuardrailAttribute ─────────────────────────────────────

/// <summary>Mark a method as an Agentspan guardrail worker.</summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class GuardrailAttribute : Attribute
{
    public string? Name { get; set; }
    public Position Position   { get; set; } = Position.Output;
    public OnFail   OnFail     { get; set; } = OnFail.Raise;
    public int      MaxRetries { get; set; } = 3;

    public GuardrailAttribute() { }
    public GuardrailAttribute(string name) { Name = name; }
}

// ── GuardrailDef ────────────────────────────────────────────

/// <summary>A compiled guardrail — name, position, on_fail, and the backing handler.</summary>
public sealed class GuardrailDef
{
    public string   Name      { get; init; } = "";
    public Position Position  { get; init; } = Position.Output;
    public OnFail   OnFail    { get; init; } = OnFail.Raise;
    public int      MaxRetries { get; init; } = 3;

    // Handler receives the content string and returns a GuardrailResult.
    internal Func<string, Task<GuardrailResult>>? Handler { get; init; }
}

// ── GuardrailRegistry ──────────────────────────────────────

/// <summary>Build <see cref="GuardrailDef"/> instances from class instances using reflection.</summary>
public static class GuardrailRegistry
{
    public static List<GuardrailDef> FromInstance(object instance)
    {
        var type = instance.GetType();
        var defs = new List<GuardrailDef>();

        foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
        {
            var attr = method.GetCustomAttribute<GuardrailAttribute>();
            if (attr is null) continue;

            var name = attr.Name ?? ToolRegistry.ToSnakeCase(method.Name);
            defs.Add(new GuardrailDef
            {
                Name       = name,
                Position   = attr.Position,
                OnFail     = attr.OnFail,
                MaxRetries = attr.MaxRetries,
                Handler    = BuildHandler(instance, method),
            });
        }
        return defs;
    }

    private static Func<string, Task<GuardrailResult>> BuildHandler(object instance, MethodInfo method)
    {
        return async (content) =>
        {
            var parameters = method.GetParameters();
            var args = new object?[parameters.Length];
            if (parameters.Length > 0) args[0] = content;

            var result = method.Invoke(instance, args);
            if (result is Task<GuardrailResult> taskResult) return await taskResult;
            if (result is GuardrailResult gr) return gr;
            return new GuardrailResult(true);
        };
    }
}

// ── RegexGuardrail ─────────────────────────────────────────

/// <summary>
/// A guardrail that validates content against regex patterns.
/// Block mode (default): fails if any pattern matches.
/// Allow mode: fails if NO pattern matches.
/// </summary>
public static class RegexGuardrail
{
    public static GuardrailDef Create(
        IEnumerable<string> patterns,
        string  mode       = "block",
        string? name       = null,
        string? message    = null,
        Position position  = Position.Output,
        OnFail  onFail     = OnFail.Retry,
        int     maxRetries = 3)
    {
        if (mode != "block" && mode != "allow")
            throw new ArgumentException($"Invalid mode '{mode}'. Must be 'block' or 'allow'.", nameof(mode));

        var compiled = patterns.Select(p => new Regex(p, RegexOptions.Compiled)).ToList();
        var guardrailName = name ?? "regex_guardrail";

        return new GuardrailDef
        {
            Name       = guardrailName,
            Position   = position,
            OnFail     = onFail,
            MaxRetries = maxRetries,
            Handler    = content =>
            {
                bool matched = compiled.Any(rx => rx.IsMatch(content));

                if (mode == "block" && matched)
                {
                    var msg = message ?? "Content matched a blocked pattern.";
                    return Task.FromResult(new GuardrailResult(false, msg));
                }
                if (mode == "allow" && !matched)
                {
                    var msg = message ?? "Content did not match any allowed pattern.";
                    return Task.FromResult(new GuardrailResult(false, msg));
                }
                return Task.FromResult(new GuardrailResult(true));
            },
        };
    }

    /// <summary>Convenience overload accepting a single pattern string.</summary>
    public static GuardrailDef Create(
        string  pattern,
        string  mode       = "block",
        string? name       = null,
        string? message    = null,
        Position position  = Position.Output,
        OnFail  onFail     = OnFail.Retry,
        int     maxRetries = 3)
        => Create([pattern], mode, name, message, position, onFail, maxRetries);
}

// ── LLMGuardrail ───────────────────────────────────────────

/// <summary>
/// A guardrail that uses an LLM to evaluate content against a safety policy.
/// The model receives the policy + content and must respond with JSON:
///   {"passed": true/false, "reason": "..."}
///
/// Requires OPENAI_API_KEY in the environment (or set the apiKey parameter).
/// </summary>
public static class LLMGuardrail
{
    private static readonly System.Net.Http.HttpClient _http = new();

    public static GuardrailDef Create(
        string  model,
        string  policy,
        string? name       = null,
        int?    maxTokens  = null,
        Position position  = Position.Output,
        OnFail  onFail     = OnFail.Retry,
        int     maxRetries = 3,
        string? apiKey     = null)
    {
        var guardrailName = name ?? "llm_guardrail";

        return new GuardrailDef
        {
            Name       = guardrailName,
            Position   = position,
            OnFail     = onFail,
            MaxRetries = maxRetries,
            Handler    = async content =>
            {
                try
                {
                    var key  = apiKey ?? Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? "";
                    var prompt =
                        "You are a content safety evaluator. Evaluate the following content against this policy:\n\n" +
                        $"POLICY: {policy}\n\n" +
                        $"CONTENT: {content}\n\n" +
                        "Respond with ONLY a JSON object: {\"passed\": true/false, \"reason\": \"...\"}";

                    // Parse provider/model format
                    var modelName = model.Contains('/') ? model.Split('/', 2)[1] : model;
                    var provider  = model.Contains('/') ? model.Split('/', 2)[0] : "openai";

                    string apiUrl = provider switch
                    {
                        "anthropic" => "https://api.anthropic.com/v1/messages",
                        _           => "https://api.openai.com/v1/chat/completions",
                    };

                    var requestBody = new
                    {
                        model    = modelName,
                        messages = new[] { new { role = "user", content = prompt } },
                        max_tokens = maxTokens ?? 300,
                        temperature = 0,
                    };

                    var json = System.Text.Json.JsonSerializer.Serialize(requestBody);
                    using var req = new System.Net.Http.HttpRequestMessage(System.Net.Http.HttpMethod.Post, apiUrl);
                    req.Headers.Add("Authorization", $"Bearer {key}");
                    req.Content = new System.Net.Http.StringContent(json, System.Text.Encoding.UTF8, "application/json");

                    using var resp = await _http.SendAsync(req);
                    var body = await resp.Content.ReadAsStringAsync();
                    var node = System.Text.Json.Nodes.JsonNode.Parse(body);
                    var text = node?["choices"]?[0]?["message"]?["content"]?.GetValue<string>() ?? "";

                    // Parse JSON response from LLM
                    try
                    {
                        var resultNode = System.Text.Json.Nodes.JsonNode.Parse(text);
                        var passed = resultNode?["passed"]?.GetValue<bool>() ?? false;
                        var reason = resultNode?["reason"]?.GetValue<string>() ?? "";
                        return new GuardrailResult(passed, reason);
                    }
                    catch
                    {
                        // If LLM didn't return valid JSON, be conservative and fail
                        return new GuardrailResult(false, $"LLM guardrail returned unparseable response: {text[..Math.Min(200, text.Length)]}");
                    }
                }
                catch (Exception ex)
                {
                    return new GuardrailResult(false, $"LLM guardrail evaluation error: {ex.Message}");
                }
            },
        };
    }
}
