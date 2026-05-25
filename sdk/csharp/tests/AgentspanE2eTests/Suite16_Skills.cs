// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;
using Agentspan.Examples;
using Xunit;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite16_Skills
{
    private readonly E2eFixture _fixture;

    public Suite16_Skills(E2eFixture fixture) => _fixture = fixture;

    [SkippableFact]
    public async Task Skill_LoadsPlansAndWorkersAreDeterministic()
    {
        _fixture.RequireServer();
        using var temp = new TempSkillDir();

        var agent = Skill.Load(temp.Path, Settings.LlmModel);
        Assert.Equal("cs_test_skill", agent.Name);
        Assert.Equal("skill", agent.Framework);
        Assert.NotNull(agent.FrameworkConfig);

        var workers = Skill.CreateSkillWorkers(agent);
        var workerNames = workers.Select(w => w.Name).Order().ToArray();
        Assert.Equal(["cs_test_skill__echo_args", "cs_test_skill__read_skill_file"], workerNames);

        var echo = workers.Single(w => w.Name.EndsWith("__echo_args", StringComparison.Ordinal));
        var echoResult = await echo.Handler(new Dictionary<string, object?> { ["command"] = "hello world" });
        Assert.Contains("ECHO_ARGS_RESULT:hello world", Convert.ToString(echoResult));

        var read = workers.Single(w => w.Name.EndsWith("__read_skill_file", StringComparison.Ordinal));
        var guide = await read.Handler(new Dictionary<string, object?> { ["path"] = "references/guide.md" });
        Assert.Contains("CS_REFERENCE_GUIDE", Convert.ToString(guide));
        var denied = await read.Handler(new Dictionary<string, object?> { ["path"] = "../SKILL.md" });
        Assert.Contains("ERROR:", Convert.ToString(denied));

        var withParams = Skill.Load(
            temp.Path,
            Settings.LlmModel,
            parameters: new Dictionary<string, object?> { ["mode"] = "slow", ["rounds"] = 2 });
        Assert.NotNull(withParams.FrameworkConfig);
        var cfg = withParams.FrameworkConfig!;
        Assert.Contains("[Skill Parameters]", Convert.ToString(cfg["skillMd"]));
        var merged = Assert.IsType<Dictionary<string, object?>>(cfg["params"]);
        Assert.Equal("slow", merged["mode"]);
        Assert.Equal(2, merged["rounds"]);

        using var cross = new TempCrossSkillDir();
        var crossAgent = Skill.Load(cross.ParentPath, Settings.LlmModel);
        var crossRefs = Assert.IsType<Dictionary<string, object>>(crossAgent.FrameworkConfig!["crossSkillRefs"]);
        var childRef = Assert.IsType<Dictionary<string, object>>(crossRefs["child-skill"]);
        var nestedRefs = Assert.IsType<Dictionary<string, object>>(childRef["crossSkillRefs"]);
        Assert.Contains("grandchild-skill", nestedRefs.Keys);

        using var search = new TempSearchPathSkillDir();
        var searchAgent = Skill.Load(search.ParentPath, Settings.LlmModel, searchPath: [search.SearchRoot]);
        var searchRefs = Assert.IsType<Dictionary<string, object>>(searchAgent.FrameworkConfig!["crossSkillRefs"]);
        Assert.Contains("external-child", searchRefs.Keys);

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var wf = plan?["workflowDef"] ?? throw new Exception("plan missing workflowDef");
        var wfText = wf.ToJsonString();
        Assert.Contains("cs_test_skill__alpha", wfText);
        Assert.Contains("cs_test_skill__beta", wfText);
        Assert.Contains("cs_test_skill__echo_args", wfText);
        Assert.Contains("cs_test_skill__read_skill_file", wfText);
        Assert.Contains("references/guide.md", wfText);
    }

    [SkippableFact]
    public async Task Skill_AsAgentToolCarriesWorkerNamesForDomainRouting()
    {
        _fixture.RequireServer();
        using var temp = new TempSkillDir();

        var skillAgent = Skill.Load(temp.Path, Settings.LlmModel);
        var skillTool = AgentTool.Create(skillAgent, description: "Run C# test skill");
        var parent = new Agent("cs_parent_with_skill_tool")
        {
            Model = Settings.LlmModel,
            Instructions = "Use the cs_test_skill tool once, then return its result.",
            Tools = [skillTool],
            Stateful = true,
            MaxTurns = 3,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);
        var planText = plan?.ToJsonString() ?? "";
        Assert.Contains("workerNames", planText);
        Assert.Contains("cs_test_skill__echo_args", planText);
        Assert.Contains("cs_test_skill__read_skill_file", planText);
        Assert.Contains("cs_test_skill", planText);
    }

    [SkippableFact]
    public async Task StandaloneSkill_ScriptRunsAsWorkerTool()
    {
        _fixture.RequireServer();
        using var temp = new TempSkillDir();

        var agent = Skill.Load(temp.Path, Settings.LlmModel);
        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(
            agent,
            "cs_tool_parity. Call cs_test_skill__echo_args exactly once with "
                + "cs_tool_parity as the command argument, then return the tool output.");

        Assert.True(result.IsSuccess,
            $"Standalone skill run must complete. executionId={result.ExecutionId} status={result.Status} error={result.Error}");

        var workflow = await _fixture.FetchWorkflowAsync(result.ExecutionId);
        VerifyWorkerTask(workflow, "cs_test_skill__echo_args", "ECHO_ARGS_RESULT:cs_tool_parity");
    }

    private static void VerifyWorkerTask(JsonNode? workflow, string taskName, string marker)
    {
        var tasks = workflow?["tasks"]?.AsArray()
            ?? throw new Exception("workflow missing tasks");
        var matches = tasks
            .Where(t =>
                (t?["taskDefName"]?.GetValue<string>() ?? "").Contains(taskName, StringComparison.Ordinal)
                || (t?["referenceTaskName"]?.GetValue<string>() ?? "").Contains(taskName, StringComparison.Ordinal)
                || (t?["taskType"]?.GetValue<string>() ?? "").Contains(taskName, StringComparison.Ordinal))
            .ToArray();

        Assert.NotEmpty(matches);
        foreach (var task in matches)
            Assert.Equal("COMPLETED", task?["status"]?.GetValue<string>());
        Assert.Contains(matches, task => (task?["outputData"]?.ToJsonString() ?? "").Contains(marker, StringComparison.Ordinal));
    }

    private sealed class TempSkillDir : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"agentspan-csharp-skill-{Guid.NewGuid():N}");

        public TempSkillDir()
        {
            Directory.CreateDirectory(Path);
            File.WriteAllText(System.IO.Path.Combine(Path, "SKILL.md"), string.Join('\n', [
                "---",
                "name: cs_test_skill",
                "params:",
                "  mode:",
                "    default: fast",
                "---",
                "## Overview",
                "A deterministic C# SDK test skill with sub-agents and a script.",
                "",
                "## Workflow",
                "1. If no prior tool result is available, call the cs_test_skill__echo_args tool exactly once.",
                "2. Pass the original user's input as the argument.",
                "3. After a tool result containing ECHO_ARGS_RESULT: is available, return that exact line as the final answer.",
                "4. If asked to continue, do not call any tool. Return the most recent ECHO_ARGS_RESULT: line exactly.",
            ]));
            File.WriteAllText(System.IO.Path.Combine(Path, "alpha-agent.md"), "# Alpha Agent\nYou analyze the input.\n");
            File.WriteAllText(System.IO.Path.Combine(Path, "beta-agent.md"), "# Beta Agent\nYou summarize the analysis.\n");

            var refs = System.IO.Path.Combine(Path, "references");
            Directory.CreateDirectory(refs);
            File.WriteAllText(System.IO.Path.Combine(refs, "guide.md"), "# CS_REFERENCE_GUIDE\nUse this deterministic guide.\n");

            var scripts = System.IO.Path.Combine(Path, "scripts");
            Directory.CreateDirectory(scripts);
            File.WriteAllText(System.IO.Path.Combine(scripts, "echo_args.py"), string.Join('\n', [
                "#!/usr/bin/env python3",
                "import sys",
                "args = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'no-args'",
                "print(f'ECHO_ARGS_RESULT:{args}')",
            ]));
        }

        public void Dispose()
        {
            try { Directory.Delete(Path, recursive: true); } catch { }
        }
    }

    private sealed class TempCrossSkillDir : IDisposable
    {
        public string Root { get; } = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"agentspan-csharp-cross-skill-{Guid.NewGuid():N}");

        public string ParentPath => System.IO.Path.Combine(Root, "parent-skill");

        public TempCrossSkillDir()
        {
            Directory.CreateDirectory(ParentPath);
            var child = System.IO.Path.Combine(Root, "child-skill");
            var grandchild = System.IO.Path.Combine(Root, "grandchild-skill");
            Directory.CreateDirectory(child);
            Directory.CreateDirectory(grandchild);

            File.WriteAllText(System.IO.Path.Combine(ParentPath, "SKILL.md"), string.Join('\n', [
                "---",
                "name: parent-skill",
                "---",
                "# Parent",
                "Use the child-skill skill.",
            ]));
            File.WriteAllText(System.IO.Path.Combine(child, "SKILL.md"), string.Join('\n', [
                "---",
                "name: child-skill",
                "---",
                "# Child",
                "Use the grandchild-skill skill.",
            ]));
            File.WriteAllText(System.IO.Path.Combine(grandchild, "SKILL.md"), string.Join('\n', [
                "---",
                "name: grandchild-skill",
                "---",
                "# Grandchild",
            ]));
        }

        public void Dispose()
        {
            try { Directory.Delete(Root, recursive: true); } catch { }
        }
    }

    private sealed class TempSearchPathSkillDir : IDisposable
    {
        public string Root { get; } = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(),
            $"agentspan-csharp-search-skill-{Guid.NewGuid():N}");

        public string ParentPath => System.IO.Path.Combine(Root, "parent");
        public string SearchRoot => System.IO.Path.Combine(Root, "external");

        public TempSearchPathSkillDir()
        {
            Directory.CreateDirectory(ParentPath);
            var child = System.IO.Path.Combine(SearchRoot, "external-child");
            Directory.CreateDirectory(child);

            File.WriteAllText(System.IO.Path.Combine(ParentPath, "SKILL.md"), string.Join('\n', [
                "---",
                "name: search-parent",
                "---",
                "# Parent",
                "Use the external-child skill.",
            ]));
            File.WriteAllText(System.IO.Path.Combine(child, "SKILL.md"), string.Join('\n', [
                "---",
                "name: external-child",
                "---",
                "# External child",
            ]));
        }

        public void Dispose()
        {
            try { Directory.Delete(Root, recursive: true); } catch { }
        }
    }
}
