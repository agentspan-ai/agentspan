// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Conductor.AI;

/// <summary>
/// Base class for condition-based handoff triggers.
///
/// <para>Handoffs transfer control from one agent to another in a SWARM. They are
/// evaluated by the <c>{agent}_handoff_check</c> worker as a fallback when no
/// transfer tool was called — based on text mentions, tool results, or a custom
/// predicate. Build entries with <see cref="OnTextMention"/>,
/// <see cref="OnToolResult"/>, or <see cref="OnCondition"/>.</para>
/// </summary>
public abstract class Handoff
{
    /// <summary>Name of the agent to transfer control to.</summary>
    public string Target { get; }

    protected Handoff(string target)
    {
        if (string.IsNullOrWhiteSpace(target))
            throw new ArgumentException("Handoff target cannot be empty.", nameof(target));
        Target = target;
    }

    /// <summary>
    /// Returns true if this trigger fires for the given context. The context
    /// carries <c>result</c> (latest agent output), <c>messages</c>,
    /// <c>tool_name</c>, and <c>tool_result</c> — mirroring the Python/Java
    /// handoff context shape.
    /// </summary>
    public abstract bool ShouldHandoff(IReadOnlyDictionary<string, object?> context);

    private protected static string Str(IReadOnlyDictionary<string, object?> ctx, string key)
        => ctx.TryGetValue(key, out var v) ? v?.ToString() ?? "" : "";
}

/// <summary>Triggers a handoff when the agent output contains a specific text.</summary>
/// <example><code>OnTextMention.Of("refund", "refund_specialist")</code></example>
public sealed class OnTextMention : Handoff
{
    public string Text { get; }

    public OnTextMention(string text, string target) : base(target) => Text = text;

    public static OnTextMention Of(string text, string target) => new(text, target);

    public override bool ShouldHandoff(IReadOnlyDictionary<string, object?> context)
        => Str(context, "result").Contains(Text, StringComparison.Ordinal);
}

/// <summary>
/// Triggers a handoff when a specific tool returns a result (optionally
/// containing a substring).
/// </summary>
/// <example><code>
/// OnToolResult.Of("check_eligibility", "refund_specialist");
/// OnToolResult.Of("check_eligibility", "refund_specialist", "eligible");
/// </code></example>
public sealed class OnToolResult : Handoff
{
    public string  ToolName       { get; }
    public string? ResultContains { get; }

    public OnToolResult(string toolName, string target, string? resultContains = null) : base(target)
    {
        ToolName       = toolName;
        ResultContains = resultContains;
    }

    public static OnToolResult Of(string toolName, string target) => new(toolName, target);

    public static OnToolResult Of(string toolName, string target, string resultContains)
        => new(toolName, target, resultContains);

    public override bool ShouldHandoff(IReadOnlyDictionary<string, object?> context)
    {
        if (!string.Equals(Str(context, "tool_name"), ToolName, StringComparison.Ordinal))
            return false;
        return ResultContains is null
            || Str(context, "tool_result").Contains(ResultContains, StringComparison.Ordinal);
    }
}

/// <summary>
/// Hands off when a custom predicate returns true. The predicate receives the
/// current agent context map. Serialized with a <c>{agentName}_handoff_{target}</c>
/// task name and evaluated locally inside the SWARM handoff-check worker.
/// </summary>
/// <example><code>
/// new OnCondition("supervisor", ctx =&gt;
///     ctx.TryGetValue("result", out var r) &amp;&amp; (r?.ToString()?.Length ?? 0) &gt; 500);
/// </code></example>
public sealed class OnCondition : Handoff
{
    public Func<IReadOnlyDictionary<string, object?>, bool> Condition { get; }

    public OnCondition(string target, Func<IReadOnlyDictionary<string, object?>, bool> condition)
        : base(target)
        => Condition = condition ?? throw new ArgumentNullException(nameof(condition));

    public override bool ShouldHandoff(IReadOnlyDictionary<string, object?> context)
        => Condition(context);
}
