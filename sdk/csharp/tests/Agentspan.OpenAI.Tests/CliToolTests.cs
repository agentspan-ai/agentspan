// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.OpenAI.Tests;

/// <summary>
/// Unit tests for <see cref="CliTool.Tokenize"/> — the command-line tokenizer
/// that lets the run_command tool accept a full command line packed into the
/// `command` field (as LLMs routinely produce). No LLM or server involved.
/// Parity target: Python cli_config.py (shlex) and TypeScript cli-config.ts.
/// </summary>
public class CliToolTests
{
    [Fact]
    public void TokenizesBareExecutable()
    {
        Assert.Equal(new[] { "git" }, CliTool.Tokenize("git"));
    }

    [Fact]
    public void TokenizesFullCommandLine()
    {
        Assert.Equal(
            new[] { "gh", "repo", "list", "--limit", "5" },
            CliTool.Tokenize("gh repo list --limit 5"));
    }

    [Fact]
    public void CollapsesRepeatedWhitespace()
    {
        Assert.Equal(new[] { "git", "status", "-s" }, CliTool.Tokenize("git   status\t-s"));
    }

    [Fact]
    public void HonorsDoubleQuotedArguments()
    {
        // Naive Split(' ') would yield ["git","commit","-m","\"hello","world\""].
        Assert.Equal(
            new[] { "git", "commit", "-m", "hello world" },
            CliTool.Tokenize("git commit -m \"hello world\""));
    }

    [Fact]
    public void HonorsSingleQuotedArguments()
    {
        Assert.Equal(
            new[] { "echo", "hello world" },
            CliTool.Tokenize("echo 'hello world'"));
    }

    [Fact]
    public void FallsBackToWhitespaceSplitOnUnbalancedQuotes()
    {
        // Unbalanced quote: don't throw, degrade to naive split.
        Assert.Equal(new[] { "echo", "\"oops" }, CliTool.Tokenize("echo \"oops"));
    }

    [Fact]
    public void EmptyStringYieldsNoTokens()
    {
        Assert.Empty(CliTool.Tokenize(""));
    }
}
