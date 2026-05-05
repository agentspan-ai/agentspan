// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Agentspan;

/// <summary>Base class for composable agent termination conditions.</summary>
public abstract class TerminationCondition
{
    /// <summary>AND — both conditions must be met to terminate.</summary>
    public static TerminationCondition operator &(TerminationCondition left, TerminationCondition right)
        => new AndTermination(left, right);

    /// <summary>OR — either condition triggers termination.</summary>
    public static TerminationCondition operator |(TerminationCondition left, TerminationCondition right)
        => new OrTermination(left, right);
}

/// <summary>Terminate when the agent output contains the specified text.</summary>
public sealed class TextMentionTermination : TerminationCondition
{
    public string Text          { get; }
    public bool   CaseSensitive { get; }

    public TextMentionTermination(string text, bool caseSensitive = false)
    {
        Text          = text;
        CaseSensitive = caseSensitive;
    }
}

/// <summary>Terminate when the agent output exactly matches the stop message.</summary>
public sealed class StopMessageTermination : TerminationCondition
{
    public string StopMessage { get; }
    public StopMessageTermination(string stopMessage) => StopMessage = stopMessage;
}

/// <summary>Terminate after N total messages have been produced.</summary>
public sealed class MaxMessageTermination : TerminationCondition
{
    public int MaxMessages { get; }
    public MaxMessageTermination(int maxMessages) => MaxMessages = maxMessages;
}

/// <summary>Terminate when a token budget is exceeded.</summary>
public sealed class TokenUsageTermination : TerminationCondition
{
    public int? MaxTotalTokens      { get; }
    public int? MaxPromptTokens     { get; }
    public int? MaxCompletionTokens { get; }

    public TokenUsageTermination(
        int? maxTotalTokens      = null,
        int? maxPromptTokens     = null,
        int? maxCompletionTokens = null)
    {
        MaxTotalTokens      = maxTotalTokens;
        MaxPromptTokens     = maxPromptTokens;
        MaxCompletionTokens = maxCompletionTokens;
    }
}

/// <summary>AND composition — terminate only when ALL child conditions are met.</summary>
public sealed class AndTermination : TerminationCondition
{
    public IReadOnlyList<TerminationCondition> Conditions { get; }
    public AndTermination(TerminationCondition left, TerminationCondition right)
        => Conditions = [left, right];
}

/// <summary>OR composition — terminate when ANY child condition is met.</summary>
public sealed class OrTermination : TerminationCondition
{
    public IReadOnlyList<TerminationCondition> Conditions { get; }
    public OrTermination(TerminationCondition left, TerminationCondition right)
        => Conditions = [left, right];
}
