// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.ComponentModel;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.SemanticKernel;

namespace Agentspan.SemanticKernel;

/// <summary>
/// Bridges Microsoft Semantic Kernel plugins to Agentspan <see cref="Agent"/>.
///
/// Users who already have classes with <c>[KernelFunction]</c>-annotated methods
/// can hand them directly to <see cref="From"/> and get back a configured
/// <see cref="Agent"/> whose tools are backed by those methods.
/// </summary>
public static class SemanticKernelAgent
{
    /// <summary>
    /// Create an Agentspan <see cref="Agent"/> from one or more plugin objects.
    /// </summary>
    /// <param name="name">Agent name (must match <c>^[a-zA-Z_][a-zA-Z0-9_-]*$</c>).</param>
    /// <param name="model">LLM model string, e.g. <c>"openai/gpt-4o-mini"</c>.</param>
    /// <param name="instructions">System prompt for the agent.</param>
    /// <param name="plugins">
    /// Objects with <c>[KernelFunction]</c>-annotated methods, or <see cref="KernelPlugin"/>
    /// instances. Each plugin contributes its functions as Agentspan tools.
    /// </param>
    public static Agent From(
        string name,
        string model,
        string instructions,
        params object[] plugins)
    {
        var tools = ExtractTools(plugins);
        return new Agent(name)
        {
            Model        = model,
            Instructions = instructions,
            Tools        = tools,
        };
    }

    /// <summary>
    /// Returns <c>true</c> if <paramref name="obj"/> has at least one method
    /// annotated with <c>[KernelFunction]</c>.
    /// </summary>
    public static bool IsSemanticKernelPlugin(object? obj)
    {
        if (obj is null) return false;
        if (obj is KernelPlugin) return true;
        foreach (var m in obj.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
        {
            if (m.GetCustomAttribute<KernelFunctionAttribute>() is not null) return true;
        }
        return false;
    }

    // ── internals (visible to tests via InternalsVisibleTo if needed) ────────

    internal static List<ToolDef> ExtractTools(object[] plugins)
    {
        var tools = new List<ToolDef>();
        if (plugins is null) return tools;

        foreach (var obj in plugins)
        {
            if (obj is null) continue;

            // KernelPlugin already exposes structured metadata — use it directly.
            if (obj is KernelPlugin kp)
            {
                foreach (var fn in kp)
                {
                    tools.Add(FromKernelFunction(fn));
                }
                continue;
            }

            // Plain object: scan methods for [KernelFunction]. Wrap via
            // KernelPluginFactory so we get the same KernelFunction objects SK
            // produces internally — this means our schema-building matches SK's
            // own runtime behavior exactly.
            var plugin = KernelPluginFactory.CreateFromObject(obj);
            foreach (var fn in plugin)
            {
                tools.Add(FromKernelFunction(fn, instance: obj));
            }
        }
        return tools;
    }

    private static ToolDef FromKernelFunction(KernelFunction fn, object? instance = null)
    {
        var meta = fn.Metadata;
        var schema = BuildInputSchema(meta);

        return ToolDefFactory.Create(
            name:        meta.Name,
            description: meta.Description ?? "",
            handler:     async (args, _ctx) =>
            {
                // Invoke via the KernelFunction — SK handles its own arg
                // coercion, default values, and async unwrapping.
                var kArgs = new KernelArguments();
                foreach (var (k, v) in args)
                {
                    kArgs[k] = JsonElementToObject(v);
                }
                // A bare Kernel is enough — these functions don't need
                // connectors or services since we only invoke them locally.
                var kernel = new Kernel();
                var result = await fn.InvokeAsync(kernel, kArgs);
                return result.GetValue<object?>();
            },
            inputSchema: schema);
    }

    private static JsonObject BuildInputSchema(KernelFunctionMetadata meta)
    {
        var props = new JsonObject();
        var required = new JsonArray();

        foreach (var p in meta.Parameters)
        {
            var node = p.Schema?.RootElement is { } el
                ? JsonNode.Parse(el.GetRawText())!.AsObject()
                : InferSchema(p.ParameterType);

            if (!string.IsNullOrEmpty(p.Description) && node["description"] is null)
            {
                node["description"] = p.Description;
            }
            props[p.Name] = node;
            if (p.IsRequired) required.Add(p.Name);
        }

        return new JsonObject
        {
            ["type"]       = "object",
            ["properties"] = props,
            ["required"]   = required,
        };
    }

    private static JsonObject InferSchema(Type? type)
    {
        if (type is null) return new JsonObject { ["type"] = "string" };
        var t = Nullable.GetUnderlyingType(type) ?? type;
        return t switch
        {
            _ when t == typeof(string) => new JsonObject { ["type"] = "string" },
            _ when t == typeof(bool)   => new JsonObject { ["type"] = "boolean" },
            _ when t == typeof(int)    || t == typeof(long) ||
                  t == typeof(float)  || t == typeof(double)
                                       => new JsonObject { ["type"] = "number" },
            _                          => new JsonObject { ["type"] = "object" },
        };
    }

    private static object? JsonElementToObject(JsonElement el) => el.ValueKind switch
    {
        JsonValueKind.String => el.GetString(),
        JsonValueKind.Number => el.TryGetInt64(out var i) ? i : el.GetDouble(),
        JsonValueKind.True   => true,
        JsonValueKind.False  => false,
        JsonValueKind.Null   => null,
        _                    => el.GetRawText(),
    };
}
