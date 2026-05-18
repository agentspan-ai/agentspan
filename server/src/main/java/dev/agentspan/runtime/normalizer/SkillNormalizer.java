/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.normalizer;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.Yaml;

import dev.agentspan.runtime.model.AgentConfig;
import dev.agentspan.runtime.model.ToolConfig;

/**
 * Normalizes agentskills.io skill directories into canonical {@link AgentConfig}.
 *
 * <p>Handles SKILL.md frontmatter parsing, sub-agent discovery from {@code *-agent.md} files,
 * script tool generation, {@code read_skill_file} tool generation, and cross-skill reference
 * resolution with cycle detection.
 *
 * <p>The raw config is produced by the Python/Go/CLI SDK, which reads the skill directory
 * and packages file contents into the format expected by this normalizer.
 */
@Component
public class SkillNormalizer implements AgentConfigNormalizer {

    private static final Logger log = LoggerFactory.getLogger(SkillNormalizer.class);
    private static final Pattern FRONTMATTER_PATTERN =
            Pattern.compile("^---\\s*\\n(.*?)\\n---\\s*\\n(.*)", Pattern.DOTALL);

    /** Threshold in characters above which SKILL.md body is auto-split into sections. */
    static final int SECTION_SPLIT_THRESHOLD = 50000;

    /** Track skills being normalized on this thread to detect circular references. */
    private final ThreadLocal<Set<String>> normalizingStack = ThreadLocal.withInitial(HashSet::new);

    @Override
    public String frameworkId() {
        return "skill";
    }

    @Override
    @SuppressWarnings("unchecked")
    public AgentConfig normalize(Map<String, Object> rawConfig) {
        String skillMd = (String) rawConfig.get("skillMd");
        String model = (String) rawConfig.getOrDefault("model", "");
        Map<String, String> agentModels =
                (Map<String, String>) rawConfig.getOrDefault("agentModels", Collections.emptyMap());
        Map<String, String> agentFiles =
                (Map<String, String>) rawConfig.getOrDefault("agentFiles", Collections.emptyMap());
        Map<String, Map<String, Object>> scripts =
                (Map<String, Map<String, Object>>) rawConfig.getOrDefault("scripts", Collections.emptyMap());
        List<String> resourceFiles = (List<String>) rawConfig.getOrDefault("resourceFiles", Collections.emptyList());
        Map<String, Object> crossSkillRefs =
                (Map<String, Object>) rawConfig.getOrDefault("crossSkillRefs", Collections.emptyMap());

        // Step 1: Parse SKILL.md frontmatter
        Map<String, Object> frontmatter = parseFrontmatter(skillMd);
        String body = extractBody(skillMd);
        String name = (String) frontmatter.get("name");
        String description = (String) frontmatter.getOrDefault("description", "");

        log.info("Normalizing skill config: {}", name);

        // Step 2: Auto-split large SKILL.md bodies into sections
        Map<String, String> skillSections = Collections.emptyMap();
        if (body.length() > SECTION_SPLIT_THRESHOLD) {
            skillSections = splitIntoSections(body);
            if (!skillSections.isEmpty()) {
                String preamble = extractPreamble(body);
                body = buildSplitInstructions(description, preamble, skillSections);
                log.info(
                        "Skill '{}': body exceeded {}chars, split into {} sections",
                        name,
                        SECTION_SPLIT_THRESHOLD,
                        skillSections.size());
            }
        }

        // Step 3: Build orchestrator AgentConfig
        AgentConfig orchestrator = new AgentConfig();
        orchestrator.setName(name);
        orchestrator.setModel(model);
        orchestrator.setInstructions(body);
        orchestrator.setDescription(description);

        // Pass through metadata
        if (frontmatter.containsKey("metadata")) {
            orchestrator.setMetadata((Map<String, Object>) frontmatter.get("metadata"));
        }

        List<ToolConfig> tools = new ArrayList<>();

        // Step 4: Build sub-agents from *-agent.md files
        for (Map.Entry<String, String> entry : agentFiles.entrySet()) {
            String agentName = entry.getKey();
            String instructions = entry.getValue();
            String agentModel = agentModels.getOrDefault(agentName, model);

            AgentConfig subAgent = new AgentConfig();
            subAgent.setName(agentName);
            subAgent.setInstructions(instructions);
            subAgent.setModel(agentModel);

            String namespacedName = name + "__" + agentName;
            Map<String, Object> toolConfig = new LinkedHashMap<>();
            toolConfig.put("agentConfig", subAgent);

            // inputSchema must include "request" property so the LLM sends its
            // message under that key — the enrichToolsScript reads
            // tc.inputParameters.request to populate the sub-workflow prompt.
            Map<String, Object> agentInputSchema = new LinkedHashMap<>();
            agentInputSchema.put("type", "object");
            agentInputSchema.put(
                    "properties",
                    Map.of(
                            "request",
                            Map.of(
                                    "type",
                                    "string",
                                    "description",
                                    "The request or question to send to the " + agentName + " agent")));
            agentInputSchema.put("required", List.of("request"));

            tools.add(ToolConfig.builder()
                    .name(namespacedName)
                    .description("Invoke the " + agentName + " agent")
                    .inputSchema(agentInputSchema)
                    .toolType("agent_tool")
                    .config(toolConfig)
                    .build());

            log.debug("Skill '{}': created sub-agent tool '{}'", name, namespacedName);
        }

        // Step 5: Build tools from scripts
        for (Map.Entry<String, Map<String, Object>> entry : scripts.entrySet()) {
            String scriptName = entry.getKey();
            String namespacedName = name + "__" + scriptName;

            Map<String, Object> inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            inputSchema.put(
                    "properties",
                    Map.of(
                            "command",
                            Map.of(
                                    "type",
                                    "string",
                                    "description",
                                    "Arguments to pass to the " + scriptName + " script")));
            inputSchema.put("required", List.of("command"));

            tools.add(ToolConfig.builder()
                    .name(namespacedName)
                    .description("Run " + scriptName + " script from " + name + " skill")
                    .toolType("worker")
                    .inputSchema(inputSchema)
                    .build());

            log.debug("Skill '{}': created script tool '{}'", name, namespacedName);
        }

        // Step 6: Build read_skill_file tool
        List<String> allReadableFiles = new ArrayList<>(resourceFiles);
        // Add virtual section files if the body was split
        for (String sectionName : skillSections.keySet()) {
            allReadableFiles.add("skill_section:" + sectionName);
        }

        if (!allReadableFiles.isEmpty()) {
            String readToolName = name + "__read_skill_file";

            String readDescription = !skillSections.isEmpty()
                    ? "Read a reference file or skill section from the " + name + " skill. "
                            + "Use skill_section:* paths to load instruction sections on demand."
                    : "Read a reference or resource file from the " + name + " skill directory";

            Map<String, Object> inputSchema = new LinkedHashMap<>();
            inputSchema.put("type", "object");
            inputSchema.put(
                    "properties",
                    Map.of(
                            "path",
                            Map.of(
                                    "type", "string",
                                    "description",
                                            "Relative path within the skill directory, or skill_section:<name> for instruction sections",
                                    "enum", allReadableFiles)));
            inputSchema.put("required", List.of("path"));

            tools.add(ToolConfig.builder()
                    .name(readToolName)
                    .description(readDescription)
                    .toolType("worker")
                    .inputSchema(inputSchema)
                    .build());

            log.debug(
                    "Skill '{}': created read_skill_file tool with {} resources + {} sections",
                    name,
                    resourceFiles.size(),
                    skillSections.size());
        }

        // Step 7: Wire cross-skill references
        Set<String> stack = normalizingStack.get();
        for (Map.Entry<String, Object> entry : crossSkillRefs.entrySet()) {
            String refName = entry.getKey();
            if (stack.contains(refName)) {
                throw new IllegalArgumentException("Circular skill reference detected: '" + refName
                        + "' is already being normalized. Stack: " + stack);
            }
            stack.add(refName);
            try {
                Map<String, Object> refConfig = (Map<String, Object>) entry.getValue();
                AgentConfig refAgent = this.normalize(refConfig);

                Map<String, Object> refToolConfig = new LinkedHashMap<>();
                refToolConfig.put("agentConfig", refAgent);

                // inputSchema must include "request" property — same as sub-agent
                // tools — so the enrichToolsScript can extract the prompt.
                Map<String, Object> refInputSchema = new LinkedHashMap<>();
                refInputSchema.put("type", "object");
                refInputSchema.put(
                        "properties",
                        Map.of(
                                "request",
                                Map.of(
                                        "type",
                                        "string",
                                        "description",
                                        "The request or question to send to the " + refAgent.getName() + " agent")));
                refInputSchema.put("required", List.of("request"));

                tools.add(ToolConfig.builder()
                        .name(refAgent.getName())
                        .description(refAgent.getDescription())
                        .inputSchema(refInputSchema)
                        .toolType("agent_tool")
                        .config(refToolConfig)
                        .build());

                log.debug("Skill '{}': wired cross-skill reference '{}'", name, refName);
            } finally {
                stack.remove(refName);
            }
        }

        // Step 8: Assemble
        if (!tools.isEmpty()) {
            orchestrator.setTools(tools);
        }

        log.info(
                "Normalized skill '{}': {} sub-agents, {} scripts, {} resources",
                name,
                agentFiles.size(),
                scripts.size(),
                resourceFiles.size());

        return orchestrator;
    }

    private Map<String, Object> parseFrontmatter(String skillMd) {
        Matcher matcher = FRONTMATTER_PATTERN.matcher(skillMd);
        if (!matcher.matches()) {
            return Collections.emptyMap();
        }
        Yaml yaml = new Yaml();
        Map<String, Object> result = yaml.load(matcher.group(1));
        return result != null ? result : Collections.emptyMap();
    }

    private String extractBody(String skillMd) {
        Matcher matcher = FRONTMATTER_PATTERN.matcher(skillMd);
        if (!matcher.matches()) {
            return skillMd;
        }
        return matcher.group(2).trim();
    }

    /**
     * Split a SKILL.md body into sections by {@code ## } heading markers.
     *
     * @return ordered map of slugified-section-name to section content (heading + body)
     */
    Map<String, String> splitIntoSections(String body) {
        Map<String, String> sections = new LinkedHashMap<>();
        // Split on lines that start with "## " (level-2 headings)
        String[] parts = body.split("(?m)(?=^## )");
        for (String part : parts) {
            String trimmed = part.trim();
            if (!trimmed.startsWith("## ")) {
                continue; // skip preamble
            }
            // Extract heading text (first line)
            int newlineIdx = trimmed.indexOf('\n');
            String headingLine = newlineIdx >= 0 ? trimmed.substring(0, newlineIdx) : trimmed;
            String headingText = headingLine.substring(3).trim(); // remove "## "
            String slug = slugify(headingText);
            if (!slug.isEmpty()) {
                sections.put(slug, trimmed);
            }
        }
        return sections;
    }

    /**
     * Extract the preamble: content before the first {@code ## } heading.
     */
    String extractPreamble(String body) {
        int idx = body.indexOf("\n## ");
        if (idx < 0) {
            // Check if body starts with "## "
            if (body.startsWith("## ")) {
                return "";
            }
            return body;
        }
        return body.substring(0, idx).trim();
    }

    /**
     * Build compact orchestrator instructions with description, preamble, and TOC.
     */
    String buildSplitInstructions(String description, String preamble, Map<String, String> sections) {
        StringBuilder sb = new StringBuilder();
        if (description != null && !description.isEmpty()) {
            sb.append(description).append("\n\n");
        }
        if (!preamble.isEmpty()) {
            sb.append(preamble).append("\n\n");
        }
        sb.append("## Available sections (use read_skill_file to load):\n");
        for (Map.Entry<String, String> entry : sections.entrySet()) {
            String slug = entry.getKey();
            String content = entry.getValue();
            // Extract original heading text from section content
            String firstLine = content.split("\n", 2)[0];
            String heading =
                    firstLine.startsWith("## ") ? firstLine.substring(3).trim() : slug;
            sb.append("- skill_section:")
                    .append(slug)
                    .append(" — ")
                    .append(heading)
                    .append("\n");
        }
        return sb.toString().trim();
    }

    /**
     * Slugify a heading: lowercase, spaces to hyphens, strip special chars.
     */
    static String slugify(String text) {
        String slug = text.toLowerCase()
                .replaceAll("[^a-z0-9\\s-]", "")
                .trim()
                .replaceAll("\\s+", "-")
                .replaceAll("-+", "-");
        // Remove leading/trailing hyphens
        return slug.replaceAll("^-+|-+$", "");
    }
}
