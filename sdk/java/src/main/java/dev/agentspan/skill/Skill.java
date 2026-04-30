// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.skill;

import dev.agentspan.Agent;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Load an Agent Skills directory as an Agentspan Agent.
 *
 * <p>A skill directory must contain a {@code SKILL.md} file with YAML frontmatter (including a
 * {@code name} field) followed by the skill body. Optionally it may contain {@code *-agent.md}
 * files, a {@code scripts/} directory, and resource directories ({@code references/},
 * {@code examples/}, {@code assets/}).
 *
 * <pre>{@code
 * Agent agent = Skill.skill(Paths.get("skills/code-review"), "openai/gpt-4o");
 *
 * Map<String, Agent> all = Skill.loadSkills(Paths.get("skills"), "openai/gpt-4o");
 * }</pre>
 */
public class Skill {

    private static final Pattern FRONTMATTER = Pattern.compile("^---\\s*\\n(.*?)\\n---\\s*\\n", Pattern.DOTALL);
    private static final Pattern NAME_FIELD = Pattern.compile("(?m)^name:\\s*(.+)$");

    private Skill() {}

    /**
     * Load an Agent Skills directory as an Agent.
     *
     * @param path  path to the skill directory containing {@code SKILL.md}
     * @param model LLM model for the orchestrator agent (e.g. {@code "openai/gpt-4o"})
     * @return an Agent configured with the skill content
     * @throws SkillLoadError if the directory is not a valid skill
     */
    public static Agent skill(Path path, String model) {
        return skill(path, model, null);
    }

    /**
     * Load an Agent Skills directory as an Agent.
     *
     * @param path          path to the skill directory containing {@code SKILL.md}
     * @param model         LLM model for the orchestrator agent
     * @param agentModels   per-sub-agent model overrides (agent name → model string)
     * @return an Agent configured with the skill content
     * @throws SkillLoadError if the directory is not a valid skill
     */
    public static Agent skill(Path path, String model, Map<String, String> agentModels) {
        path = path.toAbsolutePath().normalize();

        Path skillMdPath = path.resolve("SKILL.md");
        if (!Files.exists(skillMdPath)) {
            throw new SkillLoadError(
                "Directory " + path + " is not a valid skill: SKILL.md not found");
        }

        String skillMd;
        try {
            skillMd = Files.readString(skillMdPath);
        } catch (IOException e) {
            throw new SkillLoadError("Failed to read SKILL.md: " + e.getMessage(), e);
        }

        String name = parseName(skillMd);
        if (name == null || name.isEmpty()) {
            throw new SkillLoadError("SKILL.md missing required 'name' field in frontmatter");
        }

        Map<String, String> agentFiles = loadAgentFiles(path);
        Map<String, Map<String, String>> scripts = loadScripts(path);
        List<String> resourceFiles = loadResourceFiles(path);

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("model", model != null ? model : "");
        rawConfig.put("agentModels", agentModels != null ? agentModels : new LinkedHashMap<>());
        rawConfig.put("skillMd", skillMd);
        rawConfig.put("agentFiles", agentFiles);
        rawConfig.put("scripts", scripts);
        rawConfig.put("resourceFiles", resourceFiles);

        return Agent.builder()
                .name(name)
                .model(model != null ? model : "")
                .framework("skill")
                .frameworkConfig(rawConfig)
                .build();
    }

    /**
     * Load all skills from a directory. Each sub-directory containing a {@code SKILL.md} is loaded.
     *
     * @param path  directory containing skill sub-directories
     * @param model default LLM model for all skills
     * @return map of skill name to Agent
     */
    public static Map<String, Agent> loadSkills(Path path, String model) {
        return loadSkills(path, model, null);
    }

    /**
     * Load all skills from a directory with per-skill model overrides.
     *
     * @param path        directory containing skill sub-directories
     * @param model       default LLM model for all skills
     * @param agentModels per-skill, per-sub-agent overrides (skill dir name → agent name → model)
     * @return map of skill name to Agent
     */
    public static Map<String, Agent> loadSkills(Path path, String model,
            Map<String, Map<String, String>> agentModels) {
        path = path.toAbsolutePath().normalize();
        Map<String, Agent> skills = new TreeMap<>();
        try (Stream<Path> dirs = Files.list(path)) {
            dirs.filter(Files::isDirectory)
                .filter(d -> Files.exists(d.resolve("SKILL.md")))
                .sorted()
                .forEach(d -> {
                    Map<String, String> overrides = agentModels != null
                        ? agentModels.getOrDefault(d.getFileName().toString(), null)
                        : null;
                    Agent agent = skill(d, model, overrides);
                    skills.put(d.getFileName().toString(), agent);
                });
        } catch (IOException e) {
            throw new SkillLoadError("Failed to list skills in " + path + ": " + e.getMessage(), e);
        }
        return skills;
    }

    private static String parseName(String skillMd) {
        Matcher fm = FRONTMATTER.matcher(skillMd);
        if (!fm.find()) return null;
        String frontmatter = fm.group(1);
        Matcher nm = NAME_FIELD.matcher(frontmatter);
        if (!nm.find()) return null;
        return nm.group(1).trim();
    }

    private static Map<String, String> loadAgentFiles(Path skillDir) {
        Map<String, String> agentFiles = new TreeMap<>();
        try (Stream<Path> files = Files.list(skillDir)) {
            files.filter(f -> f.getFileName().toString().endsWith("-agent.md"))
                 .sorted()
                 .forEach(f -> {
                     String agentName = f.getFileName().toString()
                         .replaceAll("-agent\\.md$", "");
                     try {
                         agentFiles.put(agentName, Files.readString(f));
                     } catch (IOException e) {
                         throw new SkillLoadError("Failed to read agent file " + f + ": " + e.getMessage(), e);
                     }
                 });
        } catch (IOException e) {
            throw new SkillLoadError("Failed to list agent files: " + e.getMessage(), e);
        }
        return agentFiles;
    }

    private static Map<String, Map<String, String>> loadScripts(Path skillDir) {
        Map<String, Map<String, String>> scripts = new TreeMap<>();
        Path scriptsDir = skillDir.resolve("scripts");
        if (!Files.exists(scriptsDir)) return scripts;
        try (Stream<Path> files = Files.list(scriptsDir)) {
            files.filter(Files::isRegularFile)
                 .sorted()
                 .forEach(f -> {
                     String stem = f.getFileName().toString().replaceAll("\\.[^.]+$", "");
                     Map<String, String> info = new LinkedHashMap<>();
                     info.put("filename", f.getFileName().toString());
                     info.put("language", detectLanguage(f));
                     scripts.put(stem, info);
                 });
        } catch (IOException e) {
            throw new SkillLoadError("Failed to list scripts: " + e.getMessage(), e);
        }
        return scripts;
    }

    private static List<String> loadResourceFiles(Path skillDir) {
        List<String> resources = new ArrayList<>();
        for (String subdir : new String[]{"references", "examples", "assets"}) {
            Path d = skillDir.resolve(subdir);
            if (!Files.exists(d)) continue;
            try (Stream<Path> files = Files.walk(d)) {
                files.filter(Files::isRegularFile)
                     .sorted()
                     .forEach(f -> resources.add(skillDir.relativize(f).toString()));
            } catch (IOException e) {
                throw new SkillLoadError("Failed to list resource files in " + d + ": " + e.getMessage(), e);
            }
        }
        return resources;
    }

    private static String detectLanguage(Path file) {
        String name = file.getFileName().toString().toLowerCase();
        if (name.endsWith(".py")) return "python";
        if (name.endsWith(".sh")) return "bash";
        if (name.endsWith(".js") || name.endsWith(".mjs") || name.endsWith(".ts")) return "node";
        if (name.endsWith(".rb")) return "ruby";
        return "bash";
    }
}
