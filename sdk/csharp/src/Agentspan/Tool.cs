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
    // Server sends "execution_token" (snake_case); also accept camelCase alias
    [JsonPropertyName("execution_token")] public string? ExecutionToken { get; init; }
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
    /// <summary>Tool type: "worker" (default), "agent_tool", "external", or media types.</summary>
    internal string? ToolType { get; init; }
    /// <summary>For agent_tool: the wrapped agent and its runtime config.</summary>
    internal Agent? WrappedAgent { get; init; }
    internal int? AgentToolRetryCount { get; init; }
    internal int? AgentToolRetryDelaySeconds { get; init; }
    internal bool? AgentToolOptional { get; init; }
    /// <summary>For server-side tools (media, pdf): static config passed to Conductor.</summary>
    internal Dictionary<string, object>? Config { get; init; }
    // The backing delegate — null for remote/server-registered tools.
    internal Func<Dictionary<string, JsonElement>, ToolContext?, Task<object?>>? Handler { get; init; }
}

// ── AgentTool ──────────────────────────────────────────────

/// <summary>
/// Wrap an <see cref="Agent"/> as a callable tool (invoked as a sub-workflow).
///
/// Unlike sub-agents (which use handoff delegation), an agent tool is called
/// inline by the parent LLM like a function call. The child agent runs its
/// own workflow and returns the result as a tool output.
/// </summary>
public static class AgentTool
{
    /// <summary>Create a tool that runs the given agent as a sub-workflow.</summary>
    /// <param name="agent">The child agent to wrap.</param>
    /// <param name="name">Override tool name (defaults to the agent's name).</param>
    /// <param name="description">Override tool description.</param>
    /// <param name="retryCount">Retries on failure (default 2).</param>
    /// <param name="retryDelaySeconds">Seconds between retries (default 2).</param>
    /// <param name="optional">If true, failure doesn't fail the parent (default true).</param>
    public static ToolDef Create(
        Agent   agent,
        string? name                = null,
        string? description         = null,
        int?    retryCount          = null,
        int?    retryDelaySeconds   = null,
        bool?   optional            = null)
    {
        var schema = new JsonObject
        {
            ["type"] = "object",
            ["properties"] = new JsonObject
            {
                ["request"] = new JsonObject
                {
                    ["type"]        = "string",
                    ["description"] = "The request or question to send to this agent.",
                },
            },
            ["required"] = new JsonArray { "request" },
        };

        return new ToolDef
        {
            Name                      = name ?? agent.Name,
            Description               = description ?? $"Invoke the {agent.Name} agent",
            InputSchema               = schema,
            ToolType                  = "agent_tool",
            WrappedAgent              = agent,
            AgentToolRetryCount       = retryCount,
            AgentToolRetryDelaySeconds = retryDelaySeconds,
            AgentToolOptional         = optional,
        };
    }
}

// ── HttpTools ──────────────────────────────────────────────

/// <summary>
/// Factory for server-side HTTP tools (Conductor HttpTask).
/// No worker process is needed — the Conductor server makes the HTTP call.
/// </summary>
public static class HttpTools
{
    /// <summary>Create a tool backed by an HTTP endpoint.</summary>
    public static ToolDef Create(
        string name,
        string description,
        string url,
        string method = "GET",
        Dictionary<string, string>? headers = null,
        JsonObject? inputSchema = null,
        string[]? credentials = null)
    {
        var config = new Dictionary<string, object>
        {
            ["url"]         = url,
            ["method"]      = method.ToUpperInvariant(),
            ["headers"]     = headers ?? new(),
            ["accept"]      = new List<string> { "application/json" },
            ["contentType"] = "application/json",
        };
        return new ToolDef
        {
            Name        = name,
            Description = description,
            InputSchema = inputSchema ?? new JsonObject { ["type"] = "object", ["properties"] = new JsonObject() },
            ToolType    = "http",
            Config      = config,
            Credentials = credentials ?? [],
        };
    }
}

// ── McpTools ───────────────────────────────────────────────

/// <summary>
/// Factory for MCP server tools (Conductor ListMcpTools + CallMcpTool).
/// No worker process is needed.
/// </summary>
public static class McpTools
{
    /// <summary>Create tool(s) from an MCP server.</summary>
    public static ToolDef Create(
        string serverUrl,
        string? name = null,
        string? description = null,
        Dictionary<string, string>? headers = null,
        List<string>? toolNames = null,
        int maxTools = 64,
        string[]? credentials = null)
    {
        var config = new Dictionary<string, object>
        {
            ["server_url"] = serverUrl,
            ["max_tools"]  = maxTools,
        };
        if (headers is not null && headers.Count > 0)   config["headers"]    = headers;
        if (toolNames is not null && toolNames.Count > 0) config["tool_names"] = toolNames;

        return new ToolDef
        {
            Name        = name ?? "mcp_tools",
            Description = description ?? $"MCP tools from {serverUrl}",
            InputSchema = new JsonObject { ["type"] = "object", ["properties"] = new JsonObject() },
            ToolType    = "mcp",
            Config      = config,
            Credentials = credentials ?? [],
        };
    }
}

// ── RagTools ───────────────────────────────────────────────

/// <summary>
/// Factory for RAG tools: vector database indexing and search.
/// No worker process is needed — the Conductor server handles embedding and storage.
/// </summary>
public static class RagTools
{
    /// <summary>Create a tool that indexes documents into a vector database.</summary>
    public static ToolDef Index(
        string name,
        string description,
        string vectorDb,
        string index,
        string embeddingModelProvider,
        string embeddingModel,
        string @namespace = "default_ns",
        int? chunkSize = null,
        int? chunkOverlap = null,
        int? dimensions = null,
        JsonObject? inputSchema = null)
    {
        var schema = inputSchema ?? new JsonObject
        {
            ["type"] = "object",
            ["properties"] = new JsonObject
            {
                ["text"]     = new JsonObject { ["type"] = "string", ["description"] = "The text content to index." },
                ["docId"]    = new JsonObject { ["type"] = "string", ["description"] = "Unique document identifier." },
                ["metadata"] = new JsonObject { ["type"] = "object", ["description"] = "Optional metadata to store with the document." },
            },
            ["required"] = new JsonArray { "text", "docId" },
        };
        var config = new Dictionary<string, object>
        {
            ["taskType"]               = "LLM_INDEX_TEXT",
            ["vectorDB"]               = vectorDb,
            ["namespace"]              = @namespace,
            ["index"]                  = index,
            ["embeddingModelProvider"] = embeddingModelProvider,
            ["embeddingModel"]         = embeddingModel,
        };
        if (chunkSize.HasValue)    config["chunkSize"]    = chunkSize.Value;
        if (chunkOverlap.HasValue) config["chunkOverlap"] = chunkOverlap.Value;
        if (dimensions.HasValue)   config["dimensions"]   = dimensions.Value;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "rag_index", Config = config };
    }

    /// <summary>Create a tool that searches a vector database.</summary>
    public static ToolDef Search(
        string name,
        string description,
        string vectorDb,
        string index,
        string embeddingModelProvider,
        string embeddingModel,
        string @namespace = "default_ns",
        int maxResults = 5,
        int? dimensions = null,
        JsonObject? inputSchema = null)
    {
        var schema = inputSchema ?? new JsonObject
        {
            ["type"] = "object",
            ["properties"] = new JsonObject
            {
                ["query"] = new JsonObject { ["type"] = "string", ["description"] = "The search query." },
            },
            ["required"] = new JsonArray { "query" },
        };
        var config = new Dictionary<string, object>
        {
            ["taskType"]               = "LLM_SEARCH_INDEX",
            ["vectorDB"]               = vectorDb,
            ["namespace"]              = @namespace,
            ["index"]                  = index,
            ["embeddingModelProvider"] = embeddingModelProvider,
            ["embeddingModel"]         = embeddingModel,
            ["maxResults"]             = maxResults,
        };
        if (dimensions.HasValue) config["dimensions"] = dimensions.Value;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "rag_search", Config = config };
    }
}

// ── MediaTools ─────────────────────────────────────────────

/// <summary>
/// Factory methods for server-side media generation tools (no worker process needed).
/// The Conductor server calls the AI provider directly.
/// </summary>
public static class MediaTools
{
    /// <summary>Create a tool that generates images (Conductor GENERATE_IMAGE task).</summary>
    public static ToolDef Image(
        string name,
        string description,
        string llmProvider,
        string model,
        JsonObject? inputSchema = null,
        Dictionary<string, object>? extra = null)
    {
        var schema = inputSchema ?? DefaultImageSchema();
        var config = new Dictionary<string, object>
        {
            ["taskType"]    = "GENERATE_IMAGE",
            ["llmProvider"] = llmProvider,
            ["model"]       = model,
        };
        if (extra is not null) foreach (var (k, v) in extra) config[k] = v;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "generate_image", Config = config };
    }

    /// <summary>Create a tool that generates audio / TTS (Conductor GENERATE_AUDIO task).</summary>
    public static ToolDef Audio(
        string name,
        string description,
        string llmProvider,
        string model,
        JsonObject? inputSchema = null,
        Dictionary<string, object>? extra = null)
    {
        var schema = inputSchema ?? DefaultAudioSchema();
        var config = new Dictionary<string, object>
        {
            ["taskType"]    = "GENERATE_AUDIO",
            ["llmProvider"] = llmProvider,
            ["model"]       = model,
        };
        if (extra is not null) foreach (var (k, v) in extra) config[k] = v;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "generate_audio", Config = config };
    }

    /// <summary>Create a tool that generates video (Conductor GENERATE_VIDEO task).</summary>
    public static ToolDef Video(
        string name,
        string description,
        string llmProvider,
        string model,
        JsonObject? inputSchema = null,
        Dictionary<string, object>? extra = null)
    {
        var schema = inputSchema ?? DefaultVideoSchema();
        var config = new Dictionary<string, object>
        {
            ["taskType"]    = "GENERATE_VIDEO",
            ["llmProvider"] = llmProvider,
            ["model"]       = model,
        };
        if (extra is not null) foreach (var (k, v) in extra) config[k] = v;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "generate_video", Config = config };
    }

    /// <summary>Create a tool that generates PDFs from markdown (Conductor GENERATE_PDF task).</summary>
    public static ToolDef Pdf(
        string name = "generate_pdf",
        string description = "Generate a PDF document from markdown text.",
        JsonObject? inputSchema = null,
        Dictionary<string, object>? extra = null)
    {
        var schema = inputSchema ?? DefaultPdfSchema();
        var config = new Dictionary<string, object> { ["taskType"] = "GENERATE_PDF" };
        if (extra is not null) foreach (var (k, v) in extra) config[k] = v;
        return new ToolDef { Name = name, Description = description, InputSchema = schema, ToolType = "generate_pdf", Config = config };
    }

    private static JsonObject DefaultImageSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["prompt"]  = new JsonObject { ["type"] = "string", ["description"] = "Text description of the image to generate." },
            ["style"]   = new JsonObject { ["type"] = "string", ["description"] = "Image style: 'vivid' or 'natural'." },
            ["width"]   = new JsonObject { ["type"] = "integer", ["description"] = "Image width in pixels.", ["default"] = 1024 },
            ["height"]  = new JsonObject { ["type"] = "integer", ["description"] = "Image height in pixels.", ["default"] = 1024 },
            ["size"]    = new JsonObject { ["type"] = "string", ["description"] = "Image size (e.g. '1024x1024'). Alternative to width/height." },
            ["n"]       = new JsonObject { ["type"] = "integer", ["description"] = "Number of images to generate.", ["default"] = 1 },
        },
        ["required"] = new JsonArray { "prompt" },
    };

    private static JsonObject DefaultAudioSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["text"]  = new JsonObject { ["type"] = "string", ["description"] = "Text to convert to speech." },
            ["voice"] = new JsonObject { ["type"] = "string", ["description"] = "Voice to use.", ["enum"] = new JsonArray { "alloy", "echo", "fable", "onyx", "nova", "shimmer" }, ["default"] = "alloy" },
            ["speed"] = new JsonObject { ["type"] = "number", ["description"] = "Speech speed multiplier (0.25 to 4.0).", ["default"] = 1.0 },
        },
        ["required"] = new JsonArray { "text" },
    };

    private static JsonObject DefaultVideoSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["prompt"]   = new JsonObject { ["type"] = "string", ["description"] = "Text description of the video scene." },
            ["duration"] = new JsonObject { ["type"] = "integer", ["description"] = "Video duration in seconds.", ["default"] = 5 },
            ["size"]     = new JsonObject { ["type"] = "string", ["description"] = "Video size (e.g. '1280x720')." },
        },
        ["required"] = new JsonArray { "prompt" },
    };

    private static JsonObject DefaultPdfSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["markdown"]     = new JsonObject { ["type"] = "string", ["description"] = "Markdown text to convert to PDF." },
            ["pageSize"]     = new JsonObject { ["type"] = "string", ["description"] = "Page size: A4, LETTER, LEGAL, A3, or A5.", ["default"] = "A4" },
            ["theme"]        = new JsonObject { ["type"] = "string", ["description"] = "Style preset: 'default' or 'compact'.", ["default"] = "default" },
        },
        ["required"] = new JsonArray { "markdown" },
    };
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
            if (result is Task task)
            {
                await task;
                // Extract the result from Task<T> using dynamic dispatch
                var taskType = task.GetType();
                if (taskType.IsGenericType)
                {
                    try { return (object?)((dynamic)task).Result; }
                    catch { return null; }
                }
                return null;
            }
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
