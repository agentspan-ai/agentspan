// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Agentspan;

/// <summary>
/// Stops a sequential pipeline if the agent's output contains the given text.
///
/// <para>When attached to an agent in a sequential pipeline (<c>a &gt;&gt; b</c>),
/// the pipeline halts after this agent if its output contains the sentinel text;
/// otherwise execution continues to the next stage. Compiled entirely server-side
/// (inline check) — no worker round-trip.</para>
/// </summary>
/// <example><code>
/// var checker = new Agent("checker") { Model = "openai/gpt-4o", Gate = new TextGate("STOP") };
/// var fixer   = new Agent("fixer")   { Model = "openai/gpt-4o" };
/// var pipeline = checker &gt;&gt; fixer;
/// </code></example>
public sealed class TextGate
{
    public string Text          { get; }
    public bool   CaseSensitive { get; }

    public TextGate(string text, bool caseSensitive = true)
    {
        Text          = text;
        CaseSensitive = caseSensitive;
    }
}
