// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Op XOR invariant tests — mirror Python plans.py + TS plans.ts.
//
// Op must carry exactly one of Args (deterministic literal call) or Generate
// (LLM-driven). The C# typed builder previously placed the both-set check in
// ToJson(), letting an invalid Op live for its entire lifetime and only fail
// on serialization. Tighten to construction-time so invalid state is
// unrepresentable.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm.

using System;
using System.Collections.Generic;
using Xunit;
using Agentspan.Plans;

namespace Agentspan.E2eTests;

public sealed class Plans_OpTests
{
    [Fact]
    public void AcceptsArgsOnly()
    {
        var op = new Op("write_file", new Dictionary<string, object?> { ["path"] = "x" });
        var json = op.ToJson();
        Assert.Equal("write_file", (string?)json["tool"]);
        Assert.NotNull(json["args"]);
    }

    [Fact]
    public void AcceptsGenerateOnlyViaFactory()
    {
        var op = Op.WithGenerate(
            "write_file",
            new Generate { Instructions = "i", OutputSchema = "{\"x\":1}" });
        var json = op.ToJson();
        Assert.Equal("write_file", (string?)json["tool"]);
        Assert.NotNull(json["generate"]);
    }

    [Fact]
    public void RejectsNullArgs()
    {
        var ex = Assert.Throws<ArgumentNullException>(
            () => new Op("write_file", (Dictionary<string, object?>)null!));
        Assert.Contains("exactly one of args or generate", ex.Message);
    }

    [Fact]
    public void RejectsNullGenerate()
    {
        var ex = Assert.Throws<ArgumentNullException>(
            () => Op.WithGenerate("write_file", null!));
        Assert.Contains("exactly one of args or generate", ex.Message);
    }

    [Fact]
    public void BareConstructorWithNoFieldsIsNotPublic()
    {
        // The bare `new Op(tool)` constructor was the loophole that let an
        // invalid (neither-set) Op exist. The fix: the only way to construct
        // an Op is via `new Op(tool, args)` or `Op.WithGenerate(tool, gen)`.
        // This test pins the API surface — if someone re-introduces a public
        // single-arg constructor, this test breaks.
        var ctors = typeof(Op).GetConstructors(
            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
        foreach (var c in ctors)
        {
            var ps = c.GetParameters();
            Assert.False(
                ps.Length == 1 && ps[0].ParameterType == typeof(string),
                "Op should not expose a public single-string-arg constructor — " +
                "that loophole is what allowed a neither-set Op to exist.");
        }
    }
}
