// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Agentspan;

// ── Shared JSON options ─────────────────────────────────────

/// <summary>Shared <see cref="JsonSerializerOptions"/> for all Agentspan serialization.</summary>
public static class AgentspanJson
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = false,
    };
}

// ── ToolContext ────────────────────────────────────────────

/// <summary>Runtime context injected into tool method calls.</summary>
public record ToolContext
{
    [JsonPropertyName("sessionId")]    public string SessionId   { get; init; } = "";
    [JsonPropertyName("executionId")]  public string ExecutionId { get; init; } = "";
    [JsonPropertyName("agentName")]    public string AgentName   { get; init; } = "";
    [JsonPropertyName("metadata")]     public Dictionary<string, object>? Metadata     { get; init; }
    [JsonPropertyName("dependencies")] public Dictionary<string, object>? Dependencies { get; init; }
    [JsonPropertyName("state")]        public Dictionary<string, object>? State        { get; init; }
    [JsonPropertyName("executionToken")] public string? ExecutionToken { get; init; }
}

// ── PromptTemplate ─────────────────────────────────────────

/// <summary>Reference to a server-side prompt template with optional variable bindings.</summary>
public record PromptTemplate(
    string Name,
    Dictionary<string, string>? Variables = null,
    int? Version = null
);

// ── Tool attribute ─────────────────────────────────────────

/// <summary>Mark a method as an Agentspan tool. The method becomes a Conductor worker task.</summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class ToolAttribute : Attribute
{
    /// <summary>Override for the tool name (defaults to snake_case of method name).</summary>
    public string? Name { get; set; }
    /// <summary>Human-readable description of what the tool does.</summary>
    public string? Description { get; set; }
    /// <summary>Require human approval before executing.</summary>
    public bool ApprovalRequired { get; set; }
    /// <summary>Tool runs in an external worker (not registered locally).</summary>
    public bool External { get; set; }
    /// <summary>Run in isolated subprocess (default true).</summary>
    public bool Isolated { get; set; } = true;
    /// <summary>Execution timeout in seconds. 0 = no timeout.</summary>
    public int TimeoutSeconds { get; set; }
    /// <summary>Credential names that will be resolved and injected as env vars.</summary>
    public string[] Credentials { get; set; } = [];

    public ToolAttribute() { }
    public ToolAttribute(string description) { Description = description; }
}

// ── ToolDef ────────────────────────────────────────────────

/// <summary>A tool definition: name, schema, and optional backing handler.</summary>
public sealed class ToolDef
{
    public string Name { get; init; } = "";
    public string Description { get; init; } = "";
    public JsonObject InputSchema { get; init; } = new();
    public bool ApprovalRequired { get; init; }
    public bool External { get; init; }
    public int? TimeoutSeconds { get; init; }
    public string[] Credentials { get; init; } = [];
    // The backing delegate — null for remote/server-registered tools.
    internal Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>>? Handler { get; init; }
}

// ── ToolRegistry ───────────────────────────────────────────

/// <summary>Build <see cref="ToolDef"/> instances from class instances using reflection.</summary>
public static class ToolRegistry
{
    /// <summary>Scan an object's public methods for [Tool] attributes and return ToolDef list.</summary>
    public static List<ToolDef> FromInstance(object instance)
    {
        var type = instance.GetType();
        var defs = new List<ToolDef>();

        foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
        {
            var attr = method.GetCustomAttribute<ToolAttribute>();
            if (attr is null) continue;

            // Skip external tools — they have no local handler
            if (attr.External) continue;

            var name = attr.Name ?? ToSnakeCase(method.Name);
            var desc = attr.Description ?? $"Execute {method.Name}";
            var schema = BuildInputSchema(method);

            defs.Add(new ToolDef
            {
                Name = name,
                Description = desc,
                InputSchema = schema,
                ApprovalRequired = attr.ApprovalRequired,
                TimeoutSeconds = attr.TimeoutSeconds > 0 ? attr.TimeoutSeconds : null,
                Credentials = attr.Credentials,
                Handler = BuildHandler(instance, method),
            });
        }

        return defs;
    }

    private static Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>> BuildHandler(
        object instance, MethodInfo method)
    {
        return async (args, ctx) =>
        {
            var parameters = method.GetParameters();
            var callArgs = new object?[parameters.Length];

            for (int i = 0; i < parameters.Length; i++)
            {
                var p = parameters[i];

                // Inject ToolContext if the parameter type matches
                if (p.ParameterType == typeof(ToolContext) ||
                    Nullable.GetUnderlyingType(p.ParameterType) == typeof(ToolContext))
                {
                    callArgs[i] = ctx;
                    continue;
                }

                if (args.TryGetValue(p.Name!, out var element))
                {
                    callArgs[i] = CoerceArg(element, p.ParameterType);
                }
                else
                {
                    callArgs[i] = p.HasDefaultValue ? p.DefaultValue : null;
                }
            }

            var result = method.Invoke(instance, callArgs);
            if (result is Task<object?> taskObj) return await taskObj;
            if (result is Task task) { await task; return null; }
            return result;
        };
    }

    private static object? CoerceArg(JsonElement element, Type type)
    {
        // Handle string → target type coercion (spec §14.1)
        if (element.ValueKind == JsonValueKind.String)
        {
            if (type == typeof(string)) return element.GetString();
            if (type == typeof(int) || type == typeof(int?))
                return int.TryParse(element.GetString(), out var i) ? i : (object?)null;
            if (type == typeof(bool) || type == typeof(bool?))
            {
                var s = element.GetString()?.ToLower();
                return s is "true" or "1" or "yes" ? true : (s is "false" or "0" or "no" ? false : (object?)null);
            }
            if (type == typeof(double) || type == typeof(double?))
                return double.TryParse(element.GetString(), out var d) ? d : (object?)null;
        }

        if (type == typeof(string)) return element.ToString();
        if (type == typeof(int) || type == typeof(int?)) return element.GetInt32();
        if (type == typeof(long) || type == typeof(long?)) return element.GetInt64();
        if (type == typeof(double) || type == typeof(double?)) return element.GetDouble();
        if (type == typeof(float) || type == typeof(float?)) return (float)element.GetDouble();
        if (type == typeof(bool) || type == typeof(bool?)) return element.GetBoolean();
        return JsonSerializer.Deserialize(element.GetRawText(), type);
    }

    private static JsonObject BuildInputSchema(MethodInfo method)
    {
        var properties = new JsonObject();
        var required = new JsonArray();

        foreach (var p in method.GetParameters())
        {
            // Skip ToolContext — not a user-visible parameter
            if (p.ParameterType == typeof(ToolContext) ||
                Nullable.GetUnderlyingType(p.ParameterType) == typeof(ToolContext))
                continue;

            properties[p.Name!] = BuildTypeSchema(p.ParameterType);
            if (!p.HasDefaultValue && !IsNullable(p))
                required.Add(p.Name!);
        }

        return new JsonObject
        {
            ["type"] = "object",
            ["properties"] = properties,
            ["required"] = required,
        };
    }

    private static JsonNode BuildTypeSchema(Type type)
    {
        var unwrapped = Nullable.GetUnderlyingType(type) ?? type;
        return unwrapped switch
        {
            _ when unwrapped == typeof(string)   => new JsonObject { ["type"] = "string" },
            _ when unwrapped == typeof(int)
                || unwrapped == typeof(long)
                || unwrapped == typeof(float)
                || unwrapped == typeof(double)    => new JsonObject { ["type"] = "number" },
            _ when unwrapped == typeof(bool)     => new JsonObject { ["type"] = "boolean" },
            _                                    => new JsonObject { ["type"] = "object" },
        };
    }

    private static bool IsNullable(ParameterInfo p) =>
        Nullable.GetUnderlyingType(p.ParameterType) is not null ||
        p.CustomAttributes.Any(a => a.AttributeType.Name == "NullableAttribute");

    internal static string ToSnakeCase(string name)
    {
        var sb = new System.Text.StringBuilder();
        for (int i = 0; i < name.Length; i++)
        {
            if (char.IsUpper(name[i]) && i > 0) sb.Append('_');
            sb.Append(char.ToLower(name[i]));
        }
        return sb.ToString();
    }
}
