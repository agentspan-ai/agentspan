// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;

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
