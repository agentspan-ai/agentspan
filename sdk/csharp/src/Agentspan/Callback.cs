// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Reflection;
using System.Text.Json;

namespace Agentspan;

/// <summary>
/// Base class for composable agent lifecycle callbacks.
///
/// <para>Subclass and override the hook methods you care about. Multiple handlers
/// can be registered on one agent via <see cref="Agent.Callbacks"/>; they run in
/// list order, and the first hook to return a non-empty map short-circuits the
/// rest and is used as an override.</para>
///
/// <para>Each hook maps to a server callback position and task name:</para>
/// <list type="bullet">
///   <item><c>OnAgentStart</c> → <c>before_agent</c> → <c>{agent}_before_agent</c></item>
///   <item><c>OnAgentEnd</c>   → <c>after_agent</c>  → <c>{agent}_after_agent</c></item>
///   <item><c>OnModelStart</c> → <c>before_model</c> → <c>{agent}_before_model</c></item>
///   <item><c>OnModelEnd</c>   → <c>after_model</c>  → <c>{agent}_after_model</c></item>
///   <item><c>OnToolStart</c>  → <c>before_tool</c>  → <c>{agent}_before_tool</c></item>
///   <item><c>OnToolEnd</c>    → <c>after_tool</c>   → <c>{agent}_after_tool</c></item>
/// </list>
/// </summary>
public abstract class CallbackHandler
{
    /// <summary>Before the agent begins processing. Non-empty return overrides.</summary>
    public virtual Dictionary<string, object>? OnAgentStart(Dictionary<string, JsonElement> kwargs) => null;

    /// <summary>After the agent finishes. Non-empty return overrides.</summary>
    public virtual Dictionary<string, object>? OnAgentEnd(Dictionary<string, JsonElement> kwargs) => null;

    /// <summary>Before each LLM call. Non-empty return short-circuits the LLM.</summary>
    public virtual Dictionary<string, object>? OnModelStart(Dictionary<string, JsonElement> kwargs) => null;

    /// <summary>After each LLM call. Non-empty return replaces the response.</summary>
    public virtual Dictionary<string, object>? OnModelEnd(Dictionary<string, JsonElement> kwargs) => null;

    /// <summary>Before each tool execution. Non-empty return overrides.</summary>
    public virtual Dictionary<string, object>? OnToolStart(Dictionary<string, JsonElement> kwargs) => null;

    /// <summary>After each tool execution. Non-empty return overrides.</summary>
    public virtual Dictionary<string, object>? OnToolEnd(Dictionary<string, JsonElement> kwargs) => null;

    // ── Internal: position ↔ method mapping ──────────────────────────────

    /// <summary>(position, hook-method-name) pairs in server order.</summary>
    internal static readonly (string Position, string Method)[] Positions =
    [
        ("before_agent", nameof(OnAgentStart)),
        ("after_agent",  nameof(OnAgentEnd)),
        ("before_model", nameof(OnModelStart)),
        ("after_model",  nameof(OnModelEnd)),
        ("before_tool",  nameof(OnToolStart)),
        ("after_tool",   nameof(OnToolEnd)),
    ];

    /// <summary>True if this handler overrides the named hook (i.e. it's not the base no-op).</summary>
    internal bool Overrides(string methodName)
    {
        var m = GetType().GetMethod(methodName, BindingFlags.Public | BindingFlags.Instance);
        return m is not null && m.DeclaringType != typeof(CallbackHandler);
    }

    internal Dictionary<string, object>? Invoke(string methodName, Dictionary<string, JsonElement> kwargs)
        => methodName switch
        {
            nameof(OnAgentStart) => OnAgentStart(kwargs),
            nameof(OnAgentEnd)   => OnAgentEnd(kwargs),
            nameof(OnModelStart) => OnModelStart(kwargs),
            nameof(OnModelEnd)   => OnModelEnd(kwargs),
            nameof(OnToolStart)  => OnToolStart(kwargs),
            nameof(OnToolEnd)    => OnToolEnd(kwargs),
            _                    => null,
        };
}
