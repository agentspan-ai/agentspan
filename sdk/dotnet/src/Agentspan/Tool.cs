using System.Reflection;
using System.Text.Json;

namespace Agentspan;

/// <summary>
/// Attribute to mark a method as an agent tool.
/// </summary>
[AttributeUsage(AttributeTargets.Method, AllowMultiple = false)]
public sealed class ToolAttribute : Attribute
{
    public string? Name { get; set; }
    public string Description { get; set; } = "";
    public bool ApprovalRequired { get; set; } = false;
    public int TimeoutSeconds { get; set; } = 0; // 0 means "not set" — tool uses server default
}

/// <summary>
/// Represents a tool definition that can be passed to an agent.
/// </summary>
public sealed record ToolDef
{
    public string Name { get; init; } = "";
    public string Description { get; init; } = "";
    public Dictionary<string, object?> InputSchema { get; init; } = new();
    public Delegate? Func { get; init; }
    public bool ApprovalRequired { get; init; } = false;
    public int? TimeoutSeconds { get; init; }
    public string ToolType { get; init; } = "worker";
    public Dictionary<string, object?>? Config { get; init; }
}

/// <summary>
/// Registry for creating ToolDef instances from class instances using reflection.
/// </summary>
public static class ToolRegistry
{
    /// <summary>
    /// Scans an object instance for methods decorated with [Tool] and returns ToolDef instances.
    /// </summary>
    public static IEnumerable<ToolDef> FromInstance(object obj)
    {
        var type = obj.GetType();
        foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.Instance))
        {
            var attr = method.GetCustomAttribute<ToolAttribute>();
            if (attr == null) continue;

            var toolName = attr.Name ?? ToSnakeCase(method.Name);
            var inputSchema = BuildInputSchema(method);

            // Capture the method and object into a delegate
            var capturedMethod = method;
            var capturedObj = obj;

            Func<object?[], object?> invoker = args => capturedMethod.Invoke(capturedObj, args);

            // Build a proper delegate
            var parameters = method.GetParameters()
                .Where(p => p.ParameterType != typeof(CancellationToken))
                .ToArray();

            yield return new ToolDef
            {
                Name = toolName,
                Description = attr.Description,
                InputSchema = inputSchema,
                ApprovalRequired = attr.ApprovalRequired,
                TimeoutSeconds = attr.TimeoutSeconds > 0 ? attr.TimeoutSeconds : null,
                ToolType = "worker",
                Func = CreateDelegate(capturedObj, capturedMethod),
            };
        }
    }

    private static Delegate CreateDelegate(object obj, MethodInfo method)
    {
        // We create a Func<Dictionary<string,object?>, object?> that handles the invocation
        return new Func<Dictionary<string, object?>, object?>(inputData =>
        {
            var parameters = method.GetParameters()
                .Where(p => p.ParameterType != typeof(CancellationToken))
                .ToArray();

            var args = parameters.Select(p =>
            {
                var paramName = p.Name ?? "";
                // Try both camelCase and snake_case lookups
                if (inputData.TryGetValue(paramName, out var val) ||
                    inputData.TryGetValue(ToSnakeCase(paramName), out val))
                {
                    return ConvertValue(val, p.ParameterType);
                }
                return p.ParameterType.IsValueType ? Activator.CreateInstance(p.ParameterType) : null;
            }).ToArray();

            return method.Invoke(obj, args);
        });
    }

    private static Dictionary<string, object?> BuildInputSchema(MethodInfo method)
    {
        var properties = new Dictionary<string, object?>();
        var required = new List<string>();

        foreach (var param in method.GetParameters())
        {
            if (param.ParameterType == typeof(CancellationToken)) continue;

            var paramName = param.Name ?? "";
            properties[paramName] = new Dictionary<string, object?> { ["type"] = SchemaForType(param.ParameterType) };

            if (!param.HasDefaultValue && !param.ParameterType.IsGenericType)
                required.Add(paramName);
        }

        var schema = new Dictionary<string, object?>
        {
            ["type"] = "object",
            ["properties"] = properties,
        };
        if (required.Count > 0)
            schema["required"] = required;

        return schema;
    }

    private static string SchemaForType(Type t)
    {
        // Unwrap nullable
        var underlying = Nullable.GetUnderlyingType(t);
        if (underlying != null) return SchemaForType(underlying);

        if (t == typeof(string)) return "string";
        if (t == typeof(bool)) return "boolean";
        if (t == typeof(int) || t == typeof(long) || t == typeof(short) || t == typeof(byte)) return "integer";
        if (t == typeof(double) || t == typeof(float) || t == typeof(decimal)) return "number";
        if (t.IsArray || (t.IsGenericType && t.GetGenericTypeDefinition() == typeof(List<>))) return "array";
        return "object";
    }

    private static string ToSnakeCase(string name)
    {
        if (string.IsNullOrEmpty(name)) return name;
        var result = new System.Text.StringBuilder();
        for (int i = 0; i < name.Length; i++)
        {
            if (char.IsUpper(name[i]) && i > 0)
                result.Append('_');
            result.Append(char.ToLowerInvariant(name[i]));
        }
        return result.ToString();
    }

    private static object? ConvertValue(object? val, Type targetType)
    {
        if (val == null) return targetType.IsValueType ? Activator.CreateInstance(targetType) : null;
        if (val is System.Text.Json.JsonElement je)
        {
            return targetType == typeof(string) ? je.GetString() :
                   targetType == typeof(int) ? je.GetInt32() :
                   targetType == typeof(long) ? je.GetInt64() :
                   targetType == typeof(double) ? je.GetDouble() :
                   targetType == typeof(bool) ? je.GetBoolean() :
                   (object?)je.Deserialize(targetType);
        }
        if (targetType == typeof(string)) return val.ToString();
        try { return Convert.ChangeType(val, targetType); } catch { return val; }
    }

    /// <summary>
    /// Creates a ToolDef for an HTTP tool.
    /// </summary>
    public static ToolDef HttpTool(
        string name,
        string description,
        string url,
        string method = "GET",
        Dictionary<string, string>? headers = null,
        Dictionary<string, object?>? inputSchema = null)
    {
        var config = new Dictionary<string, object?>
        {
            ["url"] = url,
            ["method"] = method,
        };
        if (headers?.Count > 0)
            config["headers"] = headers;

        return new ToolDef
        {
            Name = name,
            Description = description,
            InputSchema = inputSchema ?? new Dictionary<string, object?> { ["type"] = "object", ["properties"] = new Dictionary<string, object?>() },
            ToolType = "http",
            Config = config,
        };
    }

    /// <summary>
    /// Creates a ToolDef for an MCP tool.
    /// </summary>
    public static ToolDef McpTool(
        string serverUrl,
        string name,
        string description,
        Dictionary<string, string>? headers = null)
    {
        var config = new Dictionary<string, object?>
        {
            ["serverUrl"] = serverUrl,
        };
        if (headers?.Count > 0)
            config["headers"] = headers;

        return new ToolDef
        {
            Name = name,
            Description = description,
            InputSchema = new Dictionary<string, object?> { ["type"] = "object", ["properties"] = new Dictionary<string, object?>() },
            ToolType = "mcp",
            Config = config,
        };
    }
}
