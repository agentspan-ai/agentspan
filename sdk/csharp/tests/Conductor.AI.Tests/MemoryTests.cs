// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Fix #1 — ConversationMemory parity with Python (messages + maxMessages,
/// trim semantics preserving system messages).
/// </summary>
public class ConversationMemoryTests
{
    [Fact]
    public void AddsUserAssistantSystem_inWireShape()
    {
        var mem = new ConversationMemory();
        mem.AddUserMessage("hi");
        mem.AddAssistantMessage("hello");
        mem.AddSystemMessage("be nice");

        var msgs = mem.ToChatMessages();
        Assert.Equal(3, msgs.Count);
        Assert.Equal("user", msgs[0]["role"]);
        Assert.Equal("hi", msgs[0]["message"]);
        Assert.Equal("assistant", msgs[1]["role"]);
        Assert.Equal("system", msgs[2]["role"]);
    }

    [Fact]
    public void Trim_keeps_system_and_drops_oldest_nonsystem()
    {
        var mem = new ConversationMemory(maxMessages: 3);
        mem.AddSystemMessage("sys");
        mem.AddUserMessage("u1");
        mem.AddAssistantMessage("a1");
        mem.AddUserMessage("u2"); // now 4 > 3 -> trim oldest non-system (u1)

        var msgs = mem.ToChatMessages();
        Assert.Equal(3, msgs.Count);
        // system preserved at its original position
        Assert.Equal("system", msgs[0]["role"]);
        Assert.Equal("sys", msgs[0]["message"]);
        // u1 dropped, a1 + u2 retained in order
        Assert.Equal("a1", msgs[1]["message"]);
        Assert.Equal("u2", msgs[2]["message"]);
    }

    [Fact]
    public void Serializes_to_messages_and_maxMessages()
    {
        var mem = new ConversationMemory(maxMessages: 10);
        mem.AddUserMessage("hi");

        var cfg = mem.ToMemoryConfig();
        Assert.True(cfg.ContainsKey("messages"));
        Assert.Equal(10, cfg["maxMessages"]);
    }

    [Fact]
    public void Empty_memory_serializes_to_empty_config()
    {
        var mem = new ConversationMemory();
        var cfg = mem.ToMemoryConfig();
        Assert.False(cfg.ContainsKey("messages"));
        Assert.False(cfg.ContainsKey("maxMessages"));
    }
}
