// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.skill;

import ai.agentspan.Agent;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
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
    private static final Pattern CROSS_SKILL =
        Pattern.compile("(?i)(?:invoke|use|call)\\s+(?:the\\s+)?([a-z][a-z0-9-]*)\\s+skill");
    private static final int SECTION_SPLIT_THRESHOLD = 50000;
    private static final Map<String, String> INTERPRETERS = Map.of(
        "python", "python3",
        "bash", "bash",
        "node", "node",
        "ruby", "ruby"
    );

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
        return skill(path, model, agentModels, null);
    }

    /**
     * Load an Agent Skills directory as an Agent with runtime parameter overrides.
     *
     * @param path          path to the skill directory containing {@code SKILL.md}
     * @param model         LLM model for the orchestrator agent
     * @param agentModels   per-sub-agent model overrides (agent name → model string)
     * @param params        runtime skill parameter overrides
     * @return an Agent configured with the skill content
     * @throws SkillLoadError if the directory is not a valid skill
     */
    public static Agent skill(Path path, String model, Map<String, String> agentModels, Map<String, Object> params) {
        return skill(path, model, agentModels, params, null);
    }

    /**
     * Load an Agent Skills directory as an Agent with runtime parameter overrides and
     * additional cross-skill search directories.
     *
     * @param path          path to the skill directory containing {@code SKILL.md}
     * @param model         LLM model for the orchestrator agent
     * @param agentModels   per-sub-agent model overrides (agent name → model string)
     * @param params        runtime skill parameter overrides
     * @param searchPath    additional directories for cross-skill reference resolution
     * @return an Agent configured with the skill content
     * @throws SkillLoadError if the directory is not a valid skill
     */
    public static Agent skill(
            Path path,
            String model,
            Map<String, String> agentModels,
            Map<String, Object> params,
            List<Path> searchPath) {
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
        Map<String, Object> defaultParams = extractDefaultParams(skillMd);
        Map<String, Object> mergedParams = new LinkedHashMap<>(defaultParams);
        if (params != null) {
            mergedParams.putAll(params);
        }
        if (!mergedParams.isEmpty()) {
            skillMd = skillMd + "\n\n" + formatSkillParams(mergedParams) + "\n";
        }

        Map<String, String> agentFiles = loadAgentFiles(path);
        Map<String, Map<String, String>> scripts = loadScripts(path);
        List<String> resourceFiles = loadResourceFiles(path);
        Map<String, String> skillSections = splitSkillSections(extractBody(skillMd));
        if (!skillSections.isEmpty()) {
            for (String section : skillSections.keySet()) {
                resourceFiles.add("skill_section:" + section);
            }
        }
        Map<String, Object> crossSkillRefs = resolveCrossSkills(skillMd, path, model, agentModels, searchPath);

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("model", model != null ? model : "");
        rawConfig.put("agentModels", agentModels != null ? agentModels : new LinkedHashMap<>());
        rawConfig.put("skillMd", skillMd);
        rawConfig.put("agentFiles", agentFiles);
        rawConfig.put("scripts", scripts);
        rawConfig.put("resourceFiles", resourceFiles);
        rawConfig.put("crossSkillRefs", crossSkillRefs);
        rawConfig.put("defaultParams", defaultParams);
        rawConfig.put("params", mergedParams);
        rawConfig.put("skillSections", skillSections);
        rawConfig.put("skillPath", path.toString());

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
        return loadSkills(path, model, agentModels, null);
    }

    /**
     * Load all skills from a directory with per-skill model overrides and explicit
     * cross-skill search directories.
     *
     * @param path        directory containing skill sub-directories
     * @param model       default LLM model for all skills
     * @param agentModels per-skill, per-sub-agent overrides (skill dir name → agent name → model)
     * @param searchPath  additional directories for cross-skill reference resolution
     * @return map of skill name to Agent
     */
    public static Map<String, Agent> loadSkills(Path path, String model,
            Map<String, Map<String, String>> agentModels, List<Path> searchPath) {
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
                    Agent agent = skill(d, model, overrides, null, searchPath);
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

    private static String extractBody(String skillMd) {
        Matcher fm = FRONTMATTER.matcher(skillMd);
        if (!fm.find()) return skillMd;
        return skillMd.substring(fm.end()).trim();
    }

    private static Map<String, Object> extractDefaultParams(String skillMd) {
        Matcher fm = FRONTMATTER.matcher(skillMd);
        if (!fm.find()) return new LinkedHashMap<>();
        Map<String, Object> params = new LinkedHashMap<>();
        String[] lines = fm.group(1).split("\\R");
        boolean inParams = false;
        String current = null;
        for (String line : lines) {
            if (line.trim().equals("params:")) {
                inParams = true;
                current = null;
                continue;
            }
            if (!inParams) continue;
            if (!line.startsWith(" ") && !line.startsWith("\t")) break;
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            if (trimmed.startsWith("default:") && current != null) {
                params.put(current, parseScalar(trimmed.substring("default:".length()).trim()));
                continue;
            }
            if (line.startsWith("  ") && !line.startsWith("    ") && trimmed.endsWith(":")) {
                current = trimmed.substring(0, trimmed.length() - 1).trim();
                params.putIfAbsent(current, "");
                continue;
            }
            if (line.startsWith("  ") && !line.startsWith("    ") && trimmed.contains(":")) {
                String[] parts = trimmed.split(":", 2);
                current = parts[0].trim();
                params.put(current, parseScalar(parts[1].trim()));
            }
        }
        return params;
    }

    private static Object parseScalar(String value) {
        if ("true".equalsIgnoreCase(value)) return true;
        if ("false".equalsIgnoreCase(value)) return false;
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException ignored) {
            return value;
        }
    }

    private static String formatSkillParams(Map<String, Object> params) {
        StringBuilder sb = new StringBuilder("[Skill Parameters]\n");
        params.keySet().stream().sorted().forEach(k -> {
            if (sb.length() > "[Skill Parameters]\n".length()) sb.append('\n');
            sb.append(k).append(": ").append(params.get(k));
        });
        return sb.toString();
    }

    private static Map<String, String> splitSkillSections(String body) {
        if (body.length() <= SECTION_SPLIT_THRESHOLD) return new LinkedHashMap<>();
        Map<String, String> sections = new LinkedHashMap<>();
        String[] parts = body.split("(?m)(?=^## )");
        for (String part : parts) {
            String trimmed = part.trim();
            if (!trimmed.startsWith("## ")) continue;
            String firstLine = trimmed.split("\\R", 2)[0];
            String slug = slugify(firstLine.substring(3).trim());
            if (!slug.isEmpty()) {
                sections.put(slug, trimmed);
            }
        }
        return sections;
    }

    private static String slugify(String text) {
        String lower = text.toLowerCase(Locale.ROOT);
        StringBuilder sb = new StringBuilder();
        boolean dash = false;
        for (int i = 0; i < lower.length(); i++) {
            char ch = lower.charAt(i);
            if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9')) {
                sb.append(ch);
                dash = false;
            } else if ((ch == ' ' || ch == '-' || ch == '\t') && sb.length() > 0 && !dash) {
                sb.append('-');
                dash = true;
            }
        }
        while (sb.length() > 0 && sb.charAt(sb.length() - 1) == '-') {
            sb.setLength(sb.length() - 1);
        }
        return sb.toString();
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
                     .forEach(f -> resources.add(relativeSkillPath(skillDir, f)));
            } catch (IOException e) {
                throw new SkillLoadError("Failed to list resource files in " + d + ": " + e.getMessage(), e);
            }
        }
        try (Stream<Path> files = Files.list(skillDir)) {
            files.filter(Files::isRegularFile)
                 .filter(f -> {
                     String name = f.getFileName().toString();
                     return !"SKILL.md".equals(name)
                         && !"skill.yaml".equals(name)
                         && !"skill.toml".equals(name)
                         && !name.endsWith("-agent.md");
                 })
                 .sorted()
                 .forEach(f -> resources.add(relativeSkillPath(skillDir, f)));
        } catch (IOException e) {
            throw new SkillLoadError("Failed to list root resource files: " + e.getMessage(), e);
        }
        return resources;
    }

    private static Map<String, Object> resolveCrossSkills(
            String skillMd, Path skillPath, String model, Map<String, String> agentModels, List<Path> searchPath) {
        return resolveCrossSkills(skillMd, skillPath, model, agentModels, searchPath, new HashSet<>());
    }

    private static Map<String, Object> resolveCrossSkills(
            String skillMd,
            Path skillPath,
            String model,
            Map<String, String> agentModels,
            List<Path> searchPath,
            Set<Path> seen) {
        Map<String, Object> refs = new LinkedHashMap<>();
        Matcher matcher = CROSS_SKILL.matcher(extractBody(skillMd));
        Set<String> names = new HashSet<>();
        while (matcher.find()) {
            names.add(matcher.group(1).toLowerCase(Locale.ROOT));
        }
        if (names.isEmpty()) return refs;

        List<Path> searchDirs = new ArrayList<>();
        searchDirs.add(skillPath.getParent());
        searchDirs.add(Paths.get(".").resolve(".agents").resolve("skills"));
        searchDirs.add(Paths.get(System.getProperty("user.home"), ".agents", "skills"));
        if (searchPath != null) {
            for (Path extra : searchPath) {
                if (extra != null) {
                    searchDirs.add(extra);
                }
            }
        }

        Path normalizedSkillPath = skillPath.toAbsolutePath().normalize();
        Set<Path> nextSeenBase = new HashSet<>(seen);
        nextSeenBase.add(normalizedSkillPath);
        for (String refName : names) {
            for (Path dir : searchDirs) {
                if (dir == null) continue;
                Path refDir = dir.resolve(refName).toAbsolutePath().normalize();
                if (refDir.equals(skillPath) || !Files.exists(refDir.resolve("SKILL.md"))) continue;
                if (nextSeenBase.contains(refDir)) {
                    throw new SkillLoadError("Circular skill reference detected: " + refName);
                }
                Set<Path> nextSeen = new HashSet<>(nextSeenBase);
                nextSeen.add(refDir);
                refs.put(refName, rawConfigForReference(refDir, model, agentModels, searchPath, nextSeen));
                break;
            }
        }
        return refs;
    }

    private static Map<String, Object> rawConfigForReference(
            Path refDir, String model, Map<String, String> agentModels, List<Path> searchPath, Set<Path> seen) {
        try {
            String refMd = Files.readString(refDir.resolve("SKILL.md"));
            Map<String, Object> defaultParams = extractDefaultParams(refMd);
            Map<String, String> sections = splitSkillSections(extractBody(refMd));
            List<String> resources = loadResourceFiles(refDir);
            for (String section : sections.keySet()) {
                resources.add("skill_section:" + section);
            }
            Map<String, Object> raw = new LinkedHashMap<>();
            raw.put("model", model != null ? model : "");
            raw.put("agentModels", agentModels != null ? agentModels : new LinkedHashMap<>());
            raw.put("skillMd", refMd);
            raw.put("agentFiles", loadAgentFiles(refDir));
            raw.put("scripts", loadScripts(refDir));
            raw.put("resourceFiles", resources);
            raw.put("crossSkillRefs", resolveCrossSkills(refMd, refDir, model, agentModels, searchPath, seen));
            raw.put("defaultParams", defaultParams);
            raw.put("params", defaultParams);
            raw.put("skillSections", sections);
            raw.put("skillPath", refDir.toString());
            return raw;
        } catch (IOException e) {
            throw new SkillLoadError("Failed to read cross-skill " + refDir + ": " + e.getMessage(), e);
        }
    }

    private static String relativeSkillPath(Path skillDir, Path file) {
        return skillDir.relativize(file).toString().replace('\\', '/');
    }

    private static String detectLanguage(Path file) {
        String name = file.getFileName().toString().toLowerCase();
        if (name.endsWith(".py")) return "python";
        if (name.endsWith(".sh")) return "bash";
        if (name.endsWith(".js") || name.endsWith(".mjs") || name.endsWith(".ts")) return "node";
        if (name.endsWith(".rb")) return "ruby";
        return "bash";
    }

    /** A local worker generated from a skill script or resource reader. */
    public static class SkillWorker {
        private final String name;
        private final String description;
        private final Function<Map<String, Object>, Object> func;

        SkillWorker(String name, String description, Function<Map<String, Object>, Object> func) {
            this.name = name;
            this.description = description;
            this.func = func;
        }

        public String getName() { return name; }
        public String getDescription() { return description; }
        public Function<Map<String, Object>, Object> getFunc() { return func; }
    }

    /** Create local workers for a skill agent's scripts and readable resource files. */
    @SuppressWarnings("unchecked")
    public static List<SkillWorker> createSkillWorkers(Agent agent) {
        if (agent == null || !"skill".equals(agent.getFramework()) || agent.getFrameworkConfig() == null) {
            return Collections.emptyList();
        }

        String skillName = agent.getName();
        Map<String, Object> config = agent.getFrameworkConfig();
        Path skillPath = Paths.get((String) config.getOrDefault("skillPath", "."))
            .toAbsolutePath()
            .normalize();
        Map<String, Map<String, String>> scripts =
            (Map<String, Map<String, String>>) config.getOrDefault("scripts", Collections.emptyMap());

        List<SkillWorker> workers = new ArrayList<>();
        for (Map.Entry<String, Map<String, String>> entry : scripts.entrySet()) {
            String toolName = entry.getKey();
            Map<String, String> info = entry.getValue();
            String filename = info.get("filename");
            if (filename == null || filename.isEmpty()) continue;

            String workerName = skillName + "__" + toolName;
            String interpreter = INTERPRETERS.getOrDefault(info.getOrDefault("language", "bash"), "bash");
            Path scriptPath = skillPath.resolve("scripts").resolve(filename).normalize();
            workers.add(new SkillWorker(
                workerName,
                "Run " + toolName + " script from " + skillName + " skill",
                input -> runScript(interpreter, scriptPath, stringValue(input.get("command")))
            ));
        }

        Set<String> allowedFiles = new HashSet<>((List<String>) config.getOrDefault("resourceFiles", List.of()));
        Map<String, String> skillSections =
            (Map<String, String>) config.getOrDefault("skillSections", Collections.emptyMap());
        if (!allowedFiles.isEmpty()) {
            workers.add(new SkillWorker(
                skillName + "__read_skill_file",
                "Read resource files from " + skillName + " skill",
                input -> readSkillFile(skillPath, allowedFiles, skillSections, stringValue(input.get("path")))
            ));
        }
        return workers;
    }

    private static String runScript(String interpreter, Path scriptPath, String command) {
        try {
            List<String> args = new ArrayList<>();
            args.add(interpreter);
            args.add(scriptPath.toString());
            args.addAll(splitArgs(command));

            ProcessBuilder pb = new ProcessBuilder(args);
            pb.directory(scriptPath.getParent().toFile());
            Process p = pb.start();
            CompletableFuture<String> stdoutFuture =
                CompletableFuture.supplyAsync(() -> readStream(p.getInputStream()));
            CompletableFuture<String> stderrFuture =
                CompletableFuture.supplyAsync(() -> readStream(p.getErrorStream()));
            boolean done = p.waitFor(300, TimeUnit.SECONDS);
            if (!done) {
                p.destroyForcibly();
                return "ERROR: Script execution timed out (300s)";
            }
            String stdout = stdoutFuture.join();
            String stderr = stderrFuture.join();
            if (p.exitValue() != 0) {
                return "ERROR (exit " + p.exitValue() + "):\n" + stderr;
            }
            return stdout;
        } catch (Exception e) {
            return "ERROR: " + e.getMessage();
        }
    }

    private static String readStream(InputStream stream) {
        try {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "";
        }
    }

    private static String readSkillFile(
            Path skillPath, Set<String> allowedFiles, Map<String, String> skillSections, String requestedPath) {
        if (!allowedFiles.contains(requestedPath)) {
            List<String> sorted = new ArrayList<>(allowedFiles);
            Collections.sort(sorted);
            return "ERROR: '" + requestedPath + "' not found. Available: " + sorted;
        }
        if (requestedPath.startsWith("skill_section:")) {
            String section = requestedPath.substring("skill_section:".length());
            return skillSections.getOrDefault(section, "ERROR: section '" + section + "' not found");
        }
        Path target = skillPath.resolve(requestedPath).normalize();
        if (!target.startsWith(skillPath)) {
            return "ERROR: '" + requestedPath + "' is outside the skill directory";
        }
        try {
            return Files.readString(target);
        } catch (IOException e) {
            return "ERROR reading '" + requestedPath + "': " + e.getMessage();
        }
    }

    private static List<String> splitArgs(String command) {
        if (command == null || command.isBlank()) return List.of();
        List<String> args = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inSingle = false;
        boolean inDouble = false;
        for (int i = 0; i < command.length(); i++) {
            char ch = command.charAt(i);
            if (ch == '\'' && !inDouble) {
                inSingle = !inSingle;
            } else if (ch == '"' && !inSingle) {
                inDouble = !inDouble;
            } else if (Character.isWhitespace(ch) && !inSingle && !inDouble) {
                if (current.length() > 0) {
                    args.add(current.toString());
                    current.setLength(0);
                }
            } else {
                current.append(ch);
            }
        }
        if (current.length() > 0) args.add(current.toString());
        return args;
    }

    private static String stringValue(Object value) {
        return value != null ? value.toString() : "";
    }
}
