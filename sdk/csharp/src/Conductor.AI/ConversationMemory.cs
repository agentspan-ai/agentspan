// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

namespace Conductor.AI;

/// <summary>
/// Manages conversation history for an agent session.
///
/// <para>
/// Stores messages in a format compatible with Conductor's
/// <c>workflow.variables</c> so that conversation state is persisted across
/// workflow executions and process restarts. Parity with Python's
/// <c>ConversationMemory</c> — serializes to <c>{messages, maxMessages}</c>.
/// </para>
/// </summary>
public sealed class ConversationMemory
{
    private readonly List<Dictionary<string, object?>> _messages = new();

    /// <param name="maxMessages">Maximum messages to retain (oldest non-system are trimmed). Null = unbounded.</param>
    public ConversationMemory(int? maxMessages = null)
    {
        MaxMessages = maxMessages;
    }

    /// <summary>Maximum messages to retain. Null = unbounded.</summary>
    public int? MaxMessages { get; }

    /// <summary>The accumulated conversation messages.</summary>
    public IReadOnlyList<Dictionary<string, object?>> Messages => _messages;

    /// <summary>Append a user message to the conversation.</summary>
    public void AddUserMessage(string content)
    {
        _messages.Add(new Dictionary<string, object?> { ["role"] = "user", ["message"] = content });
        Trim();
    }

    /// <summary>Append an assistant message to the conversation.</summary>
    public void AddAssistantMessage(string content)
    {
        _messages.Add(new Dictionary<string, object?> { ["role"] = "assistant", ["message"] = content });
        Trim();
    }

    /// <summary>Append a system message to the conversation.</summary>
    public void AddSystemMessage(string content)
    {
        _messages.Add(new Dictionary<string, object?> { ["role"] = "system", ["message"] = content });
        Trim();
    }

    /// <summary>Record a tool call in the conversation.</summary>
    public void AddToolCall(string toolName, Dictionary<string, object?> arguments, string? taskReferenceName = null)
    {
        var reference = taskReferenceName ?? $"{toolName}_ref";
        _messages.Add(new Dictionary<string, object?>
        {
            ["role"]    = "tool_call",
            ["message"] = "",
            ["tool_calls"] = new List<Dictionary<string, object?>>
            {
                new() { ["name"] = toolName, ["taskReferenceName"] = reference, ["input"] = arguments },
            },
        });
        Trim();
    }

    /// <summary>Record a tool result in the conversation.</summary>
    public void AddToolResult(string toolName, object? result, string? taskReferenceName = null)
    {
        var reference = taskReferenceName ?? $"{toolName}_ref";
        _messages.Add(new Dictionary<string, object?>
        {
            ["role"]              = "tool",
            ["message"]           = result?.ToString() ?? "",
            ["toolCallId"]        = reference,
            ["taskReferenceName"] = reference,
        });
        Trim();
    }

    /// <summary>Return messages in a format compatible with <c>ChatMessage</c>.</summary>
    public List<Dictionary<string, object?>> ToChatMessages()
        => _messages.Select(m => new Dictionary<string, object?>(m)).ToList();

    /// <summary>Clear all conversation history.</summary>
    public void Clear() => _messages.Clear();

    /// <summary>
    /// Serialize to a MemoryConfig dict matching Python's <c>_serialize_memory</c>:
    /// emits <c>messages</c> and <c>maxMessages</c> only when set.
    /// </summary>
    public Dictionary<string, object?> ToMemoryConfig()
    {
        var result = new Dictionary<string, object?>();
        if (_messages.Count > 0)        result["messages"]    = ToChatMessages();
        if (MaxMessages is > 0)         result["maxMessages"] = MaxMessages.Value;
        return result;
    }

    /// <summary>
    /// Trim messages to stay within configured limits, preserving ordering:
    /// removes the oldest non-system messages first while keeping all system
    /// messages in their original positions. Mirrors Python's <c>_trim</c>.
    /// </summary>
    private void Trim()
    {
        if (MaxMessages is not int max || max <= 0 || _messages.Count <= max)
            return;

        int systemCount = _messages.Count(m => Equals(m.GetValueOrDefault("role"), "system"));
        if (systemCount >= max)
        {
            // More system messages than budget — keep only the latest.
            var systemMsgs = _messages.Where(m => Equals(m.GetValueOrDefault("role"), "system")).ToList();
            _messages.Clear();
            _messages.AddRange(systemMsgs.Skip(Math.Max(0, systemMsgs.Count - max)));
            return;
        }

        int keepNonSystem = max - systemCount;
        int nonSystemSeen = 0;
        int cutoffIdx = _messages.Count;
        for (int i = _messages.Count - 1; i >= 0; i--)
        {
            if (!Equals(_messages[i].GetValueOrDefault("role"), "system"))
            {
                nonSystemSeen++;
                if (nonSystemSeen == keepNonSystem) { cutoffIdx = i; break; }
            }
        }

        var result = new List<Dictionary<string, object?>>();
        for (int i = 0; i < cutoffIdx; i++)
            if (Equals(_messages[i].GetValueOrDefault("role"), "system"))
                result.Add(_messages[i]);
        result.AddRange(_messages.Skip(cutoffIdx));

        _messages.Clear();
        _messages.AddRange(result);
    }
}
