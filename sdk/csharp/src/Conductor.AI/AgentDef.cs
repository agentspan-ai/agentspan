// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Reflection;

namespace Conductor.AI;

/// <summary>
/// Marks a method as an agent factory, resolved via <see cref="Agent.FromInstance(object)"/>.
///
/// <para><c>[Tool]</c> and <c>[Guardrail]</c> methods on the same object are
/// attached to each agent (all by default; filter with <see cref="Tools"/> /
/// <see cref="Guardrails"/>). The method body may return:</para>
/// <list type="bullet">
///   <item><c>void</c> — the agent is defined entirely by this attribute.</item>
///   <item><c>string</c> (no parameters) — dynamic instructions re-evaluated at
///         each serialization.</item>
///   <item><see cref="Agent"/> (no parameters) — a full factory; returned as-is.</item>
/// </list>
/// </summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class AgentDefAttribute : Attribute
{
    /// <summary>Agent name. Defaults to the snake_case method name.</summary>
    public string? Name { get; set; }
    /// <summary>"provider/model". Inherited from the parent agent when empty and used as a sub-agent.</summary>
    public string? Model { get; set; }
    /// <summary>Static system prompt. Overridden by a non-empty <c>string</c> method return.</summary>
    public string? Instructions { get; set; }
    /// <summary>Which <c>[Tool]</c> methods to attach: <c>["*"]</c> = all (default), <c>[]</c> = none, or specific names.</summary>
    public string[] Tools { get; set; } = ["*"];
    /// <summary>Which <c>[Guardrail]</c> methods to attach: <c>["*"]</c> = all (default), <c>[]</c> = none, or names.</summary>
    public string[] Guardrails { get; set; } = ["*"];
    /// <summary>Names of other <c>[AgentDef]</c> methods to use as sub-agents.</summary>
    public string[] Agents { get; set; } = [];
    /// <summary>Multi-agent strategy. Only meaningful when <see cref="Agents"/> is set.</summary>
    public Strategy Strategy { get; set; } = Strategy.Handoff;
    /// <summary>Max loop iterations. 0 = unset (server default).</summary>
    public int MaxTurns { get; set; }
    /// <summary>Max generation tokens. 0 = unset.</summary>
    public int MaxTokens { get; set; }
    /// <summary>Sampling temperature. NaN = unset.</summary>
    public double Temperature { get; set; } = double.NaN;

    public AgentDefAttribute() { }
    public AgentDefAttribute(string name) { Name = name; }
}

public sealed partial class Agent
{
    /// <summary>
    /// Resolve all <c>[AgentDef]</c>-annotated methods on an object into agents.
    /// <c>[Tool]</c> / <c>[Guardrail]</c> methods on the same object are attached
    /// (filtered per the annotation), and <c>Agents</c> names are wired as sub-agents.
    /// </summary>
    public static List<Agent> FromInstance(object instance)
    {
        var defs = DiscoverDefs(instance);
        if (defs.Count == 0)
            throw new ArgumentException(
                $"No [AgentDef]-annotated methods found on {instance.GetType().Name}.");

        var allTools      = ToolRegistry.FromInstance(instance);
        var allGuardrails = GuardrailRegistry.FromInstance(instance);
        var building      = new HashSet<string>();
        var built         = new Dictionary<string, Agent>(StringComparer.Ordinal);

        return defs.Keys
            .Select(name => Resolve(name, instance, defs, allTools, allGuardrails, null, building, built))
            .ToList();
    }

    /// <summary>Resolve a single <c>[AgentDef]</c> method by agent name.</summary>
    public static Agent FromInstance(object instance, string name)
    {
        var defs = DiscoverDefs(instance);
        if (!defs.ContainsKey(name))
            throw new ArgumentException(
                $"No agent named '{name}' is defined on {instance.GetType().Name}. " +
                $"Available: [{string.Join(", ", defs.Keys)}].");

        var allTools      = ToolRegistry.FromInstance(instance);
        var allGuardrails = GuardrailRegistry.FromInstance(instance);
        return Resolve(name, instance, defs, allTools, allGuardrails, null,
            new HashSet<string>(), new Dictionary<string, Agent>(StringComparer.Ordinal));
    }

    private static Dictionary<string, (MethodInfo Method, AgentDefAttribute Attr)> DiscoverDefs(object instance)
    {
        var map = new Dictionary<string, (MethodInfo, AgentDefAttribute)>(StringComparer.Ordinal);
        foreach (var m in instance.GetType().GetMethods(
                     BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
        {
            var attr = m.GetCustomAttribute<AgentDefAttribute>();
            if (attr is null) continue;
            var name = attr.Name ?? ToolRegistry.ToSnakeCase(m.Name);
            map[name] = (m, attr);
        }
        return map;
    }

    private static Agent Resolve(
        string name,
        object instance,
        Dictionary<string, (MethodInfo Method, AgentDefAttribute Attr)> defs,
        List<ToolDef> allTools,
        List<GuardrailDef> allGuardrails,
        string? parentModel,
        HashSet<string> building,
        Dictionary<string, Agent> built)
    {
        if (built.TryGetValue(name, out var cached)) return cached;
        if (!building.Add(name))
            throw new InvalidOperationException($"Cyclic [AgentDef] sub-agent reference at '{name}'.");

        var (method, attr) = defs[name];
        var model = string.IsNullOrEmpty(attr.Model) ? parentModel : attr.Model;

        // Filter discovered tools / guardrails per the annotation.
        var tools      = FilterByName(allTools,      t => t.Name, attr.Tools);
        var guardrails = FilterByName(allGuardrails, g => g.Name, attr.Guardrails);

        // Resolve declared sub-agents (recursively).
        var subAgents = new List<Agent>();
        foreach (var subName in attr.Agents)
        {
            if (!defs.ContainsKey(subName))
                throw new ArgumentException(
                    $"Agent '{name}' references unknown sub-agent '{subName}'.");
            subAgents.Add(Resolve(subName, instance, defs, allTools, allGuardrails, model, building, built));
        }

        var agent = new Agent(name)
        {
            Model        = model,
            Instructions = attr.Instructions,
            Tools        = tools,
            Guardrails   = guardrails,
            MaxTurns     = attr.MaxTurns  > 0 ? attr.MaxTurns  : null,
            MaxTokens    = attr.MaxTokens > 0 ? attr.MaxTokens : null,
            Temperature  = double.IsNaN(attr.Temperature) ? null : attr.Temperature,
        };
        if (subAgents.Count > 0)
        {
            agent.Agents   = subAgents;
            agent.Strategy = attr.Strategy;
        }

        // Return-type behavior: void → attrs only; string → dynamic instructions;
        // Agent → full factory (returned as-is). Only no-parameter methods are invoked.
        var rt = method.ReturnType;
        if (method.GetParameters().Length == 0)
        {
            if (rt == typeof(Agent))
            {
                agent = (Agent)method.Invoke(instance, null)!;
            }
            else if (rt == typeof(string))
            {
                agent.InstructionsFn = () => (string?)method.Invoke(instance, null) ?? "";
            }
        }

        building.Remove(name);
        built[name] = agent;
        return agent;
    }

    private static List<T> FilterByName<T>(List<T> all, Func<T, string> nameOf, string[] filter)
    {
        if (filter.Contains("*")) return [.. all];
        if (filter.Length == 0)   return [];
        var wanted = new HashSet<string>(filter, StringComparer.Ordinal);
        return all.Where(x => wanted.Contains(nameOf(x))).ToList();
    }
}
