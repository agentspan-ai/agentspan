// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;

namespace Agentspan;

/// <summary>Thrown when a skill directory cannot be loaded.</summary>
public sealed class SkillLoadException : Exception
{
    public SkillLoadException(string message) : base(message) { }
    public SkillLoadException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>A local worker generated from a skill script or resource reader.</summary>
public sealed class SkillWorker
{
    public required string Name { get; init; }
    public required string Description { get; init; }
    public required Func<Dictionary<string, object?>, Task<object?>> Handler { get; init; }
}

/// <summary>Load agentskills.io skill directories as Agentspan agents.</summary>
public static class Skill
{
    private static readonly Regex Frontmatter = new("^---\\s*\\n(.*?)\\n---\\s*\\n", RegexOptions.Singleline);
    private static readonly Regex NameField = new("(?m)^name:\\s*(.+)$");
    private static readonly Regex CrossSkill = new("(?i)(?:invoke|use|call)\\s+(?:the\\s+)?([a-z][a-z0-9-]*)\\s+skill");
    private const int SectionSplitThreshold = 50000;

    private static readonly Dictionary<string, string> Interpreters = new()
    {
        ["python"] = "python3",
        ["bash"] = "bash",
        ["node"] = "node",
        ["ruby"] = "ruby",
    };

    /// <summary>Load a skill directory as an <see cref="Agent"/>.</summary>
    public static Agent Load(
        string path,
        string? model = null,
        Dictionary<string, string>? agentModels = null,
        Dictionary<string, object?>? parameters = null,
        IEnumerable<string>? searchPath = null)
    {
        var skillDir = ResolvePath(path);

        var skillMdPath = Path.Combine(skillDir, "SKILL.md");
        if (!File.Exists(skillMdPath))
            throw new SkillLoadException($"Directory {skillDir} is not a valid skill: SKILL.md not found");

        string skillMd;
        try { skillMd = File.ReadAllText(skillMdPath); }
        catch (Exception ex) { throw new SkillLoadException($"Failed to read SKILL.md: {ex.Message}", ex); }

        var name = ParseName(skillMd);
        if (string.IsNullOrWhiteSpace(name))
            throw new SkillLoadException("SKILL.md missing required 'name' field in frontmatter");

        var defaultParams = ExtractDefaultParams(skillMd);
        var mergedParams = new Dictionary<string, object?>(defaultParams, StringComparer.Ordinal);
        if (parameters is not null)
            foreach (var (key, value) in parameters)
                mergedParams[key] = value;
        if (mergedParams.Count > 0)
            skillMd = skillMd + "\n\n" + FormatSkillParams(mergedParams) + "\n";

        var resources = LoadResourceFiles(skillDir);
        var sections = SplitSkillSections(ExtractBody(skillMd));
        foreach (var section in sections.Keys)
            resources.Add("skill_section:" + section);

        var raw = new Dictionary<string, object>
        {
            ["model"] = model ?? "",
            ["agentModels"] = agentModels ?? new Dictionary<string, string>(),
            ["skillMd"] = skillMd,
            ["agentFiles"] = LoadAgentFiles(skillDir),
            ["scripts"] = LoadScripts(skillDir),
            ["resourceFiles"] = resources,
            ["crossSkillRefs"] = ResolveCrossSkills(skillMd, skillDir, model, agentModels, searchPath),
            ["defaultParams"] = defaultParams,
            ["params"] = mergedParams,
            ["skillSections"] = sections,
            ["skillPath"] = skillDir,
        };

        return new Agent(name)
        {
            Model = model ?? "",
            Framework = "skill",
            FrameworkConfig = raw,
        };
    }

    /// <summary>Load all skill subdirectories under <paramref name="path"/>.</summary>
    public static Dictionary<string, Agent> LoadSkills(string path, string? model = null, IEnumerable<string>? searchPath = null)
    {
        var root = ResolvePath(path);
        var skills = new Dictionary<string, Agent>(StringComparer.Ordinal);
        if (!Directory.Exists(root)) return skills;

        foreach (var dir in Directory.EnumerateDirectories(root).OrderBy(d => d, StringComparer.Ordinal))
        {
            if (!File.Exists(Path.Combine(dir, "SKILL.md"))) continue;
            skills[Path.GetFileName(dir)] = Load(dir, model, searchPath: searchPath);
        }
        return skills;
    }

    /// <summary>Create local worker handlers for a skill agent's scripts and resources.</summary>
    public static IReadOnlyList<SkillWorker> CreateSkillWorkers(Agent agent)
    {
        if (agent.Framework != "skill" || agent.FrameworkConfig is null)
            return [];

        var skillName = agent.Name;
        var skillPath = agent.FrameworkConfig.TryGetValue("skillPath", out var sp)
            ? Convert.ToString(sp) ?? "."
            : ".";
        skillPath = Path.GetFullPath(skillPath);

        var workers = new List<SkillWorker>();
        foreach (var (toolName, info) in ReadScriptMap(agent.FrameworkConfig))
        {
            if (!info.TryGetValue("filename", out var filenameObj)) continue;
            var filename = Convert.ToString(filenameObj);
            if (string.IsNullOrWhiteSpace(filename)) continue;

            var language = info.TryGetValue("language", out var langObj)
                ? Convert.ToString(langObj) ?? "bash"
                : "bash";
            var interpreter = Interpreters.TryGetValue(language, out var i) ? i : "bash";
            var scriptPath = Path.Combine(skillPath, "scripts", filename);
            var workerName = $"{skillName}__{toolName}";

            workers.Add(new SkillWorker
            {
                Name = workerName,
                Description = $"Run {toolName} script from {skillName} skill",
                Handler = input => RunScriptAsync(
                    interpreter,
                    scriptPath,
                    input.TryGetValue("command", out var c) ? Convert.ToString(c) ?? "" : ""),
            });
        }

        var allowedFiles = ReadStringList(agent.FrameworkConfig, "resourceFiles").ToHashSet(StringComparer.Ordinal);
        var skillSections = ReadStringMap(agent.FrameworkConfig, "skillSections");
        if (allowedFiles.Count > 0)
        {
            workers.Add(new SkillWorker
            {
                Name = $"{skillName}__read_skill_file",
                Description = $"Read resource files from {skillName} skill",
                Handler = input => Task.FromResult<object?>(ReadSkillFile(
                    skillPath,
                    allowedFiles,
                    skillSections,
                    input.TryGetValue("path", out var p) ? Convert.ToString(p) ?? "" : "")),
            });
        }

        return workers;
    }

    private static string? ParseName(string skillMd)
    {
        var fm = Frontmatter.Match(skillMd);
        if (!fm.Success) return null;
        var nm = NameField.Match(fm.Groups[1].Value);
        return nm.Success ? nm.Groups[1].Value.Trim() : null;
    }

    private static string ExtractBody(string skillMd)
    {
        var fm = Frontmatter.Match(skillMd);
        return fm.Success ? skillMd[fm.Length..].Trim() : skillMd;
    }

    private static Dictionary<string, object?> ExtractDefaultParams(string skillMd)
    {
        var result = new Dictionary<string, object?>(StringComparer.Ordinal);
        var fm = Frontmatter.Match(skillMd);
        if (!fm.Success) return result;
        var inParams = false;
        string? current = null;
        foreach (var line in fm.Groups[1].Value.Split('\n'))
        {
            var trimmed = line.Trim();
            if (trimmed == "params:")
            {
                inParams = true;
                current = null;
                continue;
            }
            if (!inParams) continue;
            if (!line.StartsWith(' ') && !line.StartsWith('\t')) break;
            if (string.IsNullOrWhiteSpace(trimmed)) continue;
            if (trimmed.StartsWith("default:", StringComparison.Ordinal) && current is not null)
            {
                result[current] = ParseScalar(trimmed["default:".Length..].Trim());
                continue;
            }
            if (line.StartsWith("  ", StringComparison.Ordinal) && !line.StartsWith("    ", StringComparison.Ordinal)
                && trimmed.EndsWith(':'))
            {
                current = trimmed[..^1].Trim();
                result.TryAdd(current, "");
                continue;
            }
            if (line.StartsWith("  ", StringComparison.Ordinal) && !line.StartsWith("    ", StringComparison.Ordinal)
                && trimmed.Contains(':'))
            {
                var parts = trimmed.Split(':', 2);
                current = parts[0].Trim();
                result[current] = ParseScalar(parts[1].Trim());
            }
        }
        return result;
    }

    private static object? ParseScalar(string value)
    {
        if (bool.TryParse(value, out var b)) return b;
        if (int.TryParse(value, out var i)) return i;
        return value;
    }

    private static string FormatSkillParams(Dictionary<string, object?> parameters)
    {
        var lines = parameters.OrderBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => $"{kv.Key}: {kv.Value}");
        return "[Skill Parameters]\n" + string.Join('\n', lines);
    }

    private static Dictionary<string, string> SplitSkillSections(string body)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        if (body.Length <= SectionSplitThreshold) return result;
        foreach (var part in Regex.Split(body, "(?m)(?=^## )"))
        {
            var trimmed = part.Trim();
            if (!trimmed.StartsWith("## ", StringComparison.Ordinal)) continue;
            var firstLine = trimmed.Split('\n', 2)[0];
            var slug = Slugify(firstLine[3..].Trim());
            if (!string.IsNullOrWhiteSpace(slug))
                result[slug] = trimmed;
        }
        return result;
    }

    private static string Slugify(string text)
    {
        var lower = text.ToLowerInvariant();
        var sb = new StringBuilder();
        var dash = false;
        foreach (var ch in lower)
        {
            if (char.IsAsciiLetterOrDigit(ch))
            {
                sb.Append(ch);
                dash = false;
            }
            else if ((ch == ' ' || ch == '-' || ch == '\t') && sb.Length > 0 && !dash)
            {
                sb.Append('-');
                dash = true;
            }
        }
        return sb.ToString().Trim('-');
    }

    private static Dictionary<string, string> LoadAgentFiles(string skillDir)
    {
        return Directory.EnumerateFiles(skillDir, "*-agent.md")
            .OrderBy(f => f, StringComparer.Ordinal)
            .ToDictionary(
                f => Regex.Replace(Path.GetFileName(f), "-agent\\.md$", ""),
                File.ReadAllText,
                StringComparer.Ordinal);
    }

    private static Dictionary<string, Dictionary<string, object>> LoadScripts(string skillDir)
    {
        var scriptsDir = Path.Combine(skillDir, "scripts");
        if (!Directory.Exists(scriptsDir)) return new Dictionary<string, Dictionary<string, object>>();
        return Directory.EnumerateFiles(scriptsDir)
            .OrderBy(f => f, StringComparer.Ordinal)
            .ToDictionary(
                f => Path.GetFileNameWithoutExtension(f),
                f => new Dictionary<string, object>
                {
                    ["filename"] = Path.GetFileName(f),
                    ["language"] = DetectLanguage(f),
                },
                StringComparer.Ordinal);
    }

    private static List<string> LoadResourceFiles(string skillDir)
    {
        var resources = new List<string>();
        foreach (var subdir in new[] { "references", "examples", "assets" })
        {
            var full = Path.Combine(skillDir, subdir);
            if (!Directory.Exists(full)) continue;
            resources.AddRange(Directory.EnumerateFiles(full, "*", SearchOption.AllDirectories)
                .OrderBy(f => f, StringComparer.Ordinal)
                .Select(f => RelativeSkillPath(skillDir, f)));
        }

        resources.AddRange(Directory.EnumerateFiles(skillDir)
            .Where(f =>
            {
                var name = Path.GetFileName(f);
                return name != "SKILL.md"
                    && name != "skill.yaml"
                    && name != "skill.toml"
                    && !name.EndsWith("-agent.md", StringComparison.Ordinal);
            })
            .OrderBy(f => f, StringComparer.Ordinal)
            .Select(f => RelativeSkillPath(skillDir, f)));

        return resources;
    }

    private static Dictionary<string, object> ResolveCrossSkills(
        string skillMd,
        string skillDir,
        string? model,
        Dictionary<string, string>? agentModels,
        IEnumerable<string>? searchPath)
        => ResolveCrossSkills(skillMd, skillDir, model, agentModels, searchPath, new HashSet<string>(StringComparer.Ordinal));

    private static Dictionary<string, object> ResolveCrossSkills(
        string skillMd,
        string skillDir,
        string? model,
        Dictionary<string, string>? agentModels,
        IEnumerable<string>? searchPath,
        HashSet<string> seen)
    {
        var refs = new Dictionary<string, object>(StringComparer.Ordinal);
        var names = CrossSkill.Matches(ExtractBody(skillMd))
            .Select(m => m.Groups[1].Value.ToLowerInvariant())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        if (names.Length == 0) return refs;

        var searchDirs = new List<string?>
        {
            Directory.GetParent(skillDir)?.FullName,
            Path.Combine(Directory.GetCurrentDirectory(), ".agents", "skills"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".agents", "skills"),
        };
        if (searchPath is not null)
            searchDirs.AddRange(searchPath.Select(ResolvePath));

        var normalizedSkillDir = Path.GetFullPath(skillDir);
        var baseSeen = new HashSet<string>(seen, StringComparer.Ordinal) { normalizedSkillDir };
        foreach (var name in names)
        {
            foreach (var root in searchDirs)
            {
                if (string.IsNullOrWhiteSpace(root)) continue;
                var refDir = Path.GetFullPath(Path.Combine(root, name));
                if (refDir == normalizedSkillDir || !File.Exists(Path.Combine(refDir, "SKILL.md"))) continue;
                if (baseSeen.Contains(refDir))
                    throw new SkillLoadException($"Circular skill reference detected: {name}");
                var nextSeen = new HashSet<string>(baseSeen, StringComparer.Ordinal) { refDir };
                refs[name] = RawConfigForReference(refDir, model, agentModels, searchPath, nextSeen);
                break;
            }
        }
        return refs;
    }

    private static Dictionary<string, object> RawConfigForReference(
        string refDir,
        string? model,
        Dictionary<string, string>? agentModels,
        IEnumerable<string>? searchPath,
        HashSet<string> seen)
    {
        var skillMd = File.ReadAllText(Path.Combine(refDir, "SKILL.md"));
        var defaults = ExtractDefaultParams(skillMd);
        var sections = SplitSkillSections(ExtractBody(skillMd));
        var resources = LoadResourceFiles(refDir);
        foreach (var section in sections.Keys)
            resources.Add("skill_section:" + section);
        return new Dictionary<string, object>
        {
            ["model"] = model ?? "",
            ["agentModels"] = agentModels ?? new Dictionary<string, string>(),
            ["skillMd"] = skillMd,
            ["agentFiles"] = LoadAgentFiles(refDir),
            ["scripts"] = LoadScripts(refDir),
            ["resourceFiles"] = resources,
            ["crossSkillRefs"] = ResolveCrossSkills(skillMd, refDir, model, agentModels, searchPath, seen),
            ["defaultParams"] = defaults,
            ["params"] = defaults,
            ["skillSections"] = sections,
            ["skillPath"] = refDir,
        };
    }

    private static string RelativeSkillPath(string skillDir, string file)
        => Path.GetRelativePath(skillDir, file).Replace('\\', '/');

    private static string DetectLanguage(string file)
    {
        var name = Path.GetFileName(file).ToLowerInvariant();
        if (name.EndsWith(".py", StringComparison.Ordinal)) return "python";
        if (name.EndsWith(".sh", StringComparison.Ordinal)) return "bash";
        if (name.EndsWith(".js", StringComparison.Ordinal)
            || name.EndsWith(".mjs", StringComparison.Ordinal)
            || name.EndsWith(".ts", StringComparison.Ordinal)) return "node";
        if (name.EndsWith(".rb", StringComparison.Ordinal)) return "ruby";
        return "bash";
    }

    private static async Task<object?> RunScriptAsync(string interpreter, string scriptPath, string command)
    {
        try
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo(interpreter)
            {
                WorkingDirectory = Path.GetDirectoryName(scriptPath) ?? ".",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            };
            process.StartInfo.ArgumentList.Add(scriptPath);
            foreach (var arg in SplitArgs(command))
                process.StartInfo.ArgumentList.Add(arg);

            process.Start();
            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();

            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(300));
            try { await process.WaitForExitAsync(cts.Token); }
            catch (OperationCanceledException)
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                return "ERROR: Script execution timed out (300s)";
            }

            var stdout = await stdoutTask;
            var stderr = await stderrTask;
            return process.ExitCode == 0
                ? stdout
                : $"ERROR (exit {process.ExitCode}):\n{stderr}";
        }
        catch (Exception ex)
        {
            return $"ERROR: {ex.Message}";
        }
    }

    private static string ReadSkillFile(
        string skillPath,
        HashSet<string> allowedFiles,
        Dictionary<string, string> skillSections,
        string requestedPath)
    {
        if (!allowedFiles.Contains(requestedPath))
            return $"ERROR: '{requestedPath}' not found. Available: {string.Join(", ", allowedFiles.Order())}";

        if (requestedPath.StartsWith("skill_section:", StringComparison.Ordinal))
        {
            var section = requestedPath["skill_section:".Length..];
            return skillSections.TryGetValue(section, out var body)
                ? body
                : $"ERROR: section '{section}' not found";
        }

        var root = Path.GetFullPath(skillPath);
        var rootWithSeparator = Path.EndsInDirectorySeparator(root)
            ? root
            : root + Path.DirectorySeparatorChar;
        var target = Path.GetFullPath(Path.Combine(root, requestedPath));
        if (!target.StartsWith(rootWithSeparator, StringComparison.Ordinal) && target != root)
            return $"ERROR: '{requestedPath}' is outside the skill directory";

        try { return File.ReadAllText(target); }
        catch (Exception ex) { return $"ERROR reading '{requestedPath}': {ex.Message}"; }
    }

    private static List<string> SplitArgs(string command)
    {
        if (string.IsNullOrWhiteSpace(command)) return [];
        var args = new List<string>();
        var current = new StringBuilder();
        var inSingle = false;
        var inDouble = false;
        foreach (var ch in command)
        {
            if (ch == '\'' && !inDouble) inSingle = !inSingle;
            else if (ch == '"' && !inSingle) inDouble = !inDouble;
            else if (char.IsWhiteSpace(ch) && !inSingle && !inDouble)
            {
                if (current.Length > 0)
                {
                    args.Add(current.ToString());
                    current.Clear();
                }
            }
            else current.Append(ch);
        }
        if (current.Length > 0) args.Add(current.ToString());
        return args;
    }

    private static Dictionary<string, Dictionary<string, object?>> ReadScriptMap(
        Dictionary<string, object> config)
    {
        if (!config.TryGetValue("scripts", out var scripts) || scripts is null)
            return new Dictionary<string, Dictionary<string, object?>>();

        if (scripts is Dictionary<string, Dictionary<string, object>> typed)
            return typed.ToDictionary(kv => kv.Key, kv => kv.Value.ToDictionary(x => x.Key, x => (object?)x.Value));

        if (scripts is Dictionary<string, object> loose)
        {
            var result = new Dictionary<string, Dictionary<string, object?>>();
            foreach (var (name, value) in loose)
            {
                if (value is Dictionary<string, object> objMap)
                    result[name] = objMap.ToDictionary(kv => kv.Key, kv => (object?)kv.Value);
            }
            return result;
        }

        return new Dictionary<string, Dictionary<string, object?>>();
    }

    private static IEnumerable<string> ReadStringList(Dictionary<string, object> config, string key)
    {
        if (!config.TryGetValue(key, out var value) || value is null) yield break;
        if (value is IEnumerable<string> strings)
        {
            foreach (var s in strings) yield return s;
            yield break;
        }
        if (value is IEnumerable<object> objects)
        {
            foreach (var o in objects)
                if (o is not null) yield return o.ToString() ?? "";
        }
    }

    private static Dictionary<string, string> ReadStringMap(Dictionary<string, object> config, string key)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        if (!config.TryGetValue(key, out var value) || value is null) return result;
        if (value is Dictionary<string, string> typed)
            return new Dictionary<string, string>(typed, StringComparer.Ordinal);
        if (value is Dictionary<string, object> objects)
        {
            foreach (var (k, v) in objects)
                if (v is not null) result[k] = v.ToString() ?? "";
        }
        return result;
    }

    private static string ResolvePath(string path)
    {
        if (path.StartsWith("~/", StringComparison.Ordinal))
            path = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                path[2..]);
        return Path.GetFullPath(Environment.ExpandEnvironmentVariables(path));
    }
}
