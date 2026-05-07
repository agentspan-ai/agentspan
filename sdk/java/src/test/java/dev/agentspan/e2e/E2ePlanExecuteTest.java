// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.e2e;

import dev.agentspan.Agent;
import dev.agentspan.AgentConfig;
import dev.agentspan.AgentRuntime;
import dev.agentspan.enums.AgentStatus;
import dev.agentspan.enums.Strategy;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;
import org.junit.jupiter.api.*;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Plan-Execute strategy e2e test — runs real agents with real LLM calls.
 *
 * <p>Tests the PLAN_EXECUTE strategy end-to-end:
 * <ul>
 *   <li>Planner produces a valid JSON plan</li>
 *   <li>Plan compiles to a Conductor sub-workflow</li>
 *   <li>Parallel LLM generation executes deterministically</li>
 *   <li>Static tool calls run without LLM</li>
 *   <li>Validation passes on the happy path</li>
 *   <li>Files are actually created on disk</li>
 * </ul>
 *
 * <p>All assertions are algorithmic (file existence, word counts) — no LLM
 * output is used for validation (CLAUDE.md rule).
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class E2ePlanExecuteTest extends E2eBaseTest {

    static final Path WORK_DIR = Path.of(System.getProperty("java.io.tmpdir"), "plan-execute-test-java");
    static final int MIN_WORD_COUNT = 200;

    static AgentRuntime runtime;

    @BeforeAll
    static void setUp() {
        runtime = new AgentRuntime(new AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void tearDown() {
        if (runtime != null) runtime.close();
    }

    @BeforeEach
    void cleanWorkDir() throws IOException {
        if (Files.exists(WORK_DIR)) {
            Files.walk(WORK_DIR)
                .sorted(Comparator.reverseOrder())
                .map(Path::toFile)
                .forEach(File::delete);
        }
        Files.createDirectories(WORK_DIR);
    }

    // ── Tools ────────────────────────────────────────────────────────────

    static ToolDef createDirectoryTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("path", Map.of("type", "string", "description", "Directory path to create (relative to working dir)."));

        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("path"));

        return ToolDef.builder()
            .name("create_directory")
            .description("Create a directory (and parents) if it doesn't exist.")
            .inputSchema(inputSchema)
            .toolType("worker")
            .func(input -> {
                String path = (String) input.get("path");
                Path full = WORK_DIR.resolve(path);
                try {
                    Files.createDirectories(full);
                } catch (IOException e) {
                    return "ERROR: " + e.getMessage();
                }
                return "Created directory: " + full;
            })
            .build();
    }

    static ToolDef writeFileTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("path", Map.of("type", "string", "description", "File path (relative to working dir)."));
        props.put("content", Map.of("type", "string", "description", "Full file content to write."));

        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("path", "content"));

        return ToolDef.builder()
            .name("write_file")
            .description("Write content to a file, creating parent directories if needed.")
            .inputSchema(inputSchema)
            .toolType("worker")
            .func(input -> {
                String path = (String) input.get("path");
                String content = (String) input.get("content");
                Path full = WORK_DIR.resolve(path);
                try {
                    Files.createDirectories(full.getParent());
                    Files.writeString(full, content);
                } catch (IOException e) {
                    return "ERROR: " + e.getMessage();
                }
                return "Wrote " + content.length() + " bytes to " + full;
            })
            .build();
    }

    static ToolDef readFileTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("path", Map.of("type", "string", "description", "File path (relative to working dir)."));

        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("path"));

        return ToolDef.builder()
            .name("read_file")
            .description("Read the contents of a file.")
            .inputSchema(inputSchema)
            .toolType("worker")
            .func(input -> {
                String path = (String) input.get("path");
                Path full = WORK_DIR.resolve(path);
                if (!Files.exists(full)) {
                    return "ERROR: File not found: " + full;
                }
                try {
                    return Files.readString(full);
                } catch (IOException e) {
                    return "ERROR: " + e.getMessage();
                }
            })
            .build();
    }

    static ToolDef assembleFilesTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("output_path", Map.of("type", "string", "description", "Output file path (relative to working dir)."));
        props.put("input_paths", Map.of("type", "string", "description", "JSON array of input file paths (relative to working dir)."));
        props.put("separator", Map.of("type", "string", "description", "Text to insert between file contents."));

        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("output_path", "input_paths"));

        return ToolDef.builder()
            .name("assemble_files")
            .description("Concatenate multiple files into one, with a separator between them.")
            .inputSchema(inputSchema)
            .toolType("worker")
            .func(input -> {
                String outputPath = (String) input.get("output_path");
                String inputPathsJson = (String) input.get("input_paths");
                String separator = input.get("separator") instanceof String
                    ? (String) input.get("separator") : "\n\n---\n\n";

                List<String> paths;
                try {
                    com.fasterxml.jackson.databind.ObjectMapper mapper =
                        new com.fasterxml.jackson.databind.ObjectMapper();
                    paths = mapper.readValue(inputPathsJson,
                        mapper.getTypeFactory().constructCollectionType(List.class, String.class));
                } catch (Exception e) {
                    return "ERROR: Failed to parse input_paths: " + e.getMessage();
                }

                StringBuilder combined = new StringBuilder();
                for (int i = 0; i < paths.size(); i++) {
                    if (i > 0) combined.append(separator);
                    Path full = WORK_DIR.resolve(paths.get(i));
                    if (Files.exists(full)) {
                        try {
                            combined.append(Files.readString(full));
                        } catch (IOException e) {
                            combined.append("[Error reading: ").append(paths.get(i)).append("]");
                        }
                    } else {
                        combined.append("[Missing: ").append(paths.get(i)).append("]");
                    }
                }

                Path outFull = WORK_DIR.resolve(outputPath);
                try {
                    Files.createDirectories(outFull.getParent());
                    Files.writeString(outFull, combined.toString());
                } catch (IOException e) {
                    return "ERROR: " + e.getMessage();
                }
                return "Assembled " + paths.size() + " files into " + outFull
                    + " (" + combined.length() + " bytes)";
            })
            .build();
    }

    static ToolDef checkWordCountTool() {
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("path", Map.of("type", "string", "description", "File path (relative to working dir)."));
        props.put("min_words", Map.of("type", "integer", "description", "Minimum number of words required."));

        Map<String, Object> inputSchema = new LinkedHashMap<>();
        inputSchema.put("type", "object");
        inputSchema.put("properties", props);
        inputSchema.put("required", List.of("path", "min_words"));

        return ToolDef.builder()
            .name("check_word_count")
            .description("Check that a file meets a minimum word count.")
            .inputSchema(inputSchema)
            .toolType("worker")
            .func(input -> {
                String path = (String) input.get("path");
                Object minWordsRaw = input.get("min_words");
                int minWords = minWordsRaw instanceof Number
                    ? ((Number) minWordsRaw).intValue() : 200;

                Path full = WORK_DIR.resolve(path);
                if (!Files.exists(full)) {
                    return "{\"passed\": false, \"error\": \"File not found: " + path
                        + "\", \"word_count\": 0}";
                }
                String content;
                try {
                    content = Files.readString(full);
                } catch (IOException e) {
                    return "{\"passed\": false, \"error\": \"" + e.getMessage()
                        + "\", \"word_count\": 0}";
                }
                int count = content.split("\\s+").length;
                boolean passed = count >= minWords;
                return "{\"passed\": " + passed + ", \"word_count\": " + count
                    + ", \"min_words\": " + minWords + "}";
            })
            .build();
    }

    // ── Agent instructions (max_tokens variant) ─────────────────────────

    static final String MAX_TOKENS_PLANNER_INSTRUCTIONS = "You are a research report planner. Given a topic, plan a detailed report.\n"
        + "\n"
        + "Your job:\n"
        + "1. Decide on 3 sections for the report (introduction, body, conclusion)\n"
        + "2. For each section, write clear instructions requesting DETAILED content (250+ words each)\n"
        + "3. Output your plan as Markdown with an embedded JSON fence\n"
        + "\n"
        + "IMPORTANT: Your plan MUST include a ```json fence with the structured plan.\n"
        + "IMPORTANT: Every generate block MUST include \"max_tokens\": 8192.\n"
        + "\n"
        + "## Available tools:\n"
        + "- `create_directory`: args={path}\n"
        + "- `write_file`: generate={instructions, output_schema, max_tokens}\n"
        + "- `assemble_files`: args={output_path, input_paths, separator}\n"
        + "- `check_word_count`: args={path, min_words}\n"
        + "\n"
        + "## Plan format:\n"
        + "\n"
        + "```json\n"
        + "{\n"
        + "  \"steps\": [\n"
        + "    {\n"
        + "      \"id\": \"setup\",\n"
        + "      \"parallel\": false,\n"
        + "      \"operations\": [\n"
        + "        {\"tool\": \"create_directory\", \"args\": {\"path\": \"sections\"}}\n"
        + "      ]\n"
        + "    },\n"
        + "    {\n"
        + "      \"id\": \"write_sections\",\n"
        + "      \"depends_on\": [\"setup\"],\n"
        + "      \"parallel\": true,\n"
        + "      \"operations\": [\n"
        + "        {\n"
        + "          \"tool\": \"write_file\",\n"
        + "          \"generate\": {\n"
        + "            \"instructions\": \"Write a detailed 250+ word introduction about [topic].\",\n"
        + "            \"output_schema\": \"{\\\"path\\\": \\\"sections/01_intro.md\\\", \\\"content\\\": \\\"...\\\"}\",\n"
        + "            \"max_tokens\": 8192\n"
        + "          }\n"
        + "        },\n"
        + "        {\n"
        + "          \"tool\": \"write_file\",\n"
        + "          \"generate\": {\n"
        + "            \"instructions\": \"Write a detailed 250+ word body section about [subtopic].\",\n"
        + "            \"output_schema\": \"{\\\"path\\\": \\\"sections/02_body.md\\\", \\\"content\\\": \\\"...\\\"}\",\n"
        + "            \"max_tokens\": 8192\n"
        + "          }\n"
        + "        },\n"
        + "        {\n"
        + "          \"tool\": \"write_file\",\n"
        + "          \"generate\": {\n"
        + "            \"instructions\": \"Write a detailed 250+ word conclusion about [topic].\",\n"
        + "            \"output_schema\": \"{\\\"path\\\": \\\"sections/03_conclusion.md\\\", \\\"content\\\": \\\"...\\\"}\",\n"
        + "            \"max_tokens\": 8192\n"
        + "          }\n"
        + "        }\n"
        + "      ]\n"
        + "    },\n"
        + "    {\n"
        + "      \"id\": \"assemble\",\n"
        + "      \"depends_on\": [\"write_sections\"],\n"
        + "      \"parallel\": false,\n"
        + "      \"operations\": [\n"
        + "        {\n"
        + "          \"tool\": \"assemble_files\",\n"
        + "          \"args\": {\n"
        + "            \"output_path\": \"report.md\",\n"
        + "            \"input_paths\": \"[\\\"sections/01_intro.md\\\", \\\"sections/02_body.md\\\", \\\"sections/03_conclusion.md\\\"]\",\n"
        + "            \"separator\": \"\\n\\n---\\n\\n\"\n"
        + "          }\n"
        + "        }\n"
        + "      ]\n"
        + "    }\n"
        + "  ],\n"
        + "  \"validation\": [\n"
        + "    {\"tool\": \"check_word_count\", \"args\": {\"path\": \"report.md\", \"min_words\": " + MIN_WORD_COUNT + "}}\n"
        + "  ],\n"
        + "  \"on_success\": []\n"
        + "}\n"
        + "```\n"
        + "\n"
        + "## Rules:\n"
        + "- Section files go in sections/ directory\n"
        + "- Each section MUST be 250+ words (detailed, thorough)\n"
        + "- Every generate block MUST include \"max_tokens\": 8192\n"
        + "- The assemble step must list ALL section files in order\n"
        + "- Always validate with check_word_count (min " + MIN_WORD_COUNT + " words)\n"
        + "- The JSON must be valid\n";

    // ── Agent instructions ───────────────────────────────────────────────

    static final String PLANNER_INSTRUCTIONS = "You are a research report planner. Given a topic, plan a structured report.\n"
        + "\n"
        + "Your job:\n"
        + "1. Decide on 3 sections for the report (introduction, body, conclusion)\n"
        + "2. For each section, write clear instructions on what content to include\n"
        + "3. Output your plan as Markdown with an embedded JSON fence\n"
        + "\n"
        + "IMPORTANT: Your plan MUST include a ```json fence with the structured plan.\n"
        + "\n"
        + "## Available tools for operations:\n"
        + "- `create_directory`: args={path} — create a directory\n"
        + "- `write_file`: generate={instructions, output_schema} — LLM writes content\n"
        + "- `assemble_files`: args={output_path, input_paths, separator} — concatenate files\n"
        + "- `check_word_count`: args={path, min_words} — validate word count\n"
        + "\n"
        + "## Plan format:\n"
        + "\n"
        + "Your output MUST end with a JSON fence like this example:\n"
        + "\n"
        + "```json\n"
        + "{\n"
        + "  \"steps\": [\n"
        + "    {\n"
        + "      \"id\": \"setup\",\n"
        + "      \"parallel\": false,\n"
        + "      \"operations\": [\n"
        + "        {\"tool\": \"create_directory\", \"args\": {\"path\": \"sections\"}}\n"
        + "      ]\n"
        + "    },\n"
        + "    {\n"
        + "      \"id\": \"write_sections\",\n"
        + "      \"depends_on\": [\"setup\"],\n"
        + "      \"parallel\": true,\n"
        + "      \"operations\": [\n"
        + "        {\n"
        + "          \"tool\": \"write_file\",\n"
        + "          \"generate\": {\n"
        + "            \"instructions\": \"Write a 100-word introduction about [topic].\",\n"
        + "            \"output_schema\": \"{\\\"path\\\": \\\"sections/01_intro.md\\\", \\\"content\\\": \\\"...\\\"}\"\n"
        + "          }\n"
        + "        },\n"
        + "        {\n"
        + "          \"tool\": \"write_file\",\n"
        + "          \"generate\": {\n"
        + "            \"instructions\": \"Write a 100-word section about [subtopic].\",\n"
        + "            \"output_schema\": \"{\\\"path\\\": \\\"sections/02_body.md\\\", \\\"content\\\": \\\"...\\\"}\"\n"
        + "          }\n"
        + "        }\n"
        + "      ]\n"
        + "    },\n"
        + "    {\n"
        + "      \"id\": \"assemble\",\n"
        + "      \"depends_on\": [\"write_sections\"],\n"
        + "      \"parallel\": false,\n"
        + "      \"operations\": [\n"
        + "        {\n"
        + "          \"tool\": \"assemble_files\",\n"
        + "          \"args\": {\n"
        + "            \"output_path\": \"report.md\",\n"
        + "            \"input_paths\": \"[\\\"sections/01_intro.md\\\", \\\"sections/02_body.md\\\"]\",\n"
        + "            \"separator\": \"\\n\\n---\\n\\n\"\n"
        + "          }\n"
        + "        }\n"
        + "      ]\n"
        + "    }\n"
        + "  ],\n"
        + "  \"validation\": [\n"
        + "    {\"tool\": \"check_word_count\", \"args\": {\"path\": \"report.md\", \"min_words\": " + MIN_WORD_COUNT + "}}\n"
        + "  ],\n"
        + "  \"on_success\": []\n"
        + "}\n"
        + "```\n"
        + "\n"
        + "## Rules:\n"
        + "- Section files go in sections/ directory (01_intro.md, 02_body.md, etc.)\n"
        + "- Each section should be 80-150 words\n"
        + "- The assemble step must list ALL section files in order\n"
        + "- Always validate with check_word_count (min " + MIN_WORD_COUNT + " words)\n"
        + "- Keep it simple: 3 sections total\n"
        + "- The JSON must be valid\n";

    static final String FALLBACK_INSTRUCTIONS = "You are fixing a report that failed validation. "
        + "The plan was already partially executed but something went wrong "
        + "(missing sections, word count too low, etc.).\n"
        + "\n"
        + "Review the error output, figure out what's missing or broken, and fix it.\n"
        + "You have access to read_file, write_file, assemble_files, and check_word_count.\n"
        + "\n"
        + "Working directory: " + WORK_DIR;

    // ── Tests ────────────────────────────────────────────────────────────

    /**
     * Plan-Execute should generate a report that passes word count validation.
     *
     * <p>COUNTERFACTUAL: if PLAN_EXECUTE strategy enum is not recognized by the
     * server, the workflow won't compile or execute. If tool workers don't run,
     * no files are created and file existence assertions fail. If fallbackMaxTurns
     * is not serialized, the server may reject the config.
     */
    @Test
    @Order(1)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void testReportGeneration() {
        List<ToolDef> tools = List.of(
            createDirectoryTool(),
            writeFileTool(),
            readFileTool(),
            assembleFilesTool(),
            checkWordCountTool()
        );

        Agent planner = Agent.builder()
            .name("test_java_planner")
            .model(MODEL)
            .instructions(PLANNER_INSTRUCTIONS)
            .maxTurns(3)
            .maxTokens(4000)
            .build();

        Agent fallback = Agent.builder()
            .name("test_java_fallback")
            .model(MODEL)
            .instructions(FALLBACK_INSTRUCTIONS)
            .tools(tools)
            .maxTurns(10)
            .maxTokens(8000)
            .build();

        Agent harness = Agent.builder()
            .name("test_java_report_gen")
            .model(MODEL)
            .agents(planner, fallback)
            .strategy(Strategy.PLAN_EXECUTE)
            .fallbackMaxTurns(5)
            .build();

        AgentResult result = runtime.run(harness,
            "Write a short research report about: The impact of AI on software testing");

        // 1. Workflow completed
        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent did not complete. Status: " + result.getStatus()
            + ". Error: " + result.getError());

        // 2. Report file exists
        Path reportPath = WORK_DIR.resolve("report.md");
        assertTrue(Files.exists(reportPath),
            "Report file not found at " + reportPath
            + ". COUNTERFACTUAL: if tool workers didn't execute, no files are created.");

        // 3. Report has content
        String content;
        try {
            content = Files.readString(reportPath);
        } catch (IOException e) {
            fail("Failed to read report file: " + e.getMessage());
            return;
        }
        assertTrue(content.length() > 0, "Report file is empty");

        int wordCount = content.split("\\s+").length;

        // 4. Word count meets minimum
        assertTrue(wordCount >= MIN_WORD_COUNT,
            "Report has " + wordCount + " words, expected >= " + MIN_WORD_COUNT
            + ". COUNTERFACTUAL: if plan execution skipped write steps, word count is 0.");

        // 5. Section files were created (proves parallel execution happened)
        Path sectionsDir = WORK_DIR.resolve("sections");
        assertTrue(Files.isDirectory(sectionsDir),
            "sections/ directory not created. "
            + "COUNTERFACTUAL: if create_directory tool didn't run, this directory won't exist.");

        File[] sectionFiles = sectionsDir.toFile().listFiles(
            (dir, name) -> name.endsWith(".md"));
        assertNotNull(sectionFiles, "Could not list section files");
        assertTrue(sectionFiles.length >= 2,
            "Expected >= 2 section files, found " + sectionFiles.length
            + ". COUNTERFACTUAL: parallel write_file steps must each produce a file.");

        // 6. Each section file has content
        for (File sf : sectionFiles) {
            try {
                String sfContent = Files.readString(sf.toPath());
                int sfWords = sfContent.split("\\s+").length;
                assertTrue(sfWords > 10,
                    "Section " + sf.getName() + " has only " + sfWords + " words");
            } catch (IOException e) {
                fail("Failed to read section file " + sf.getName() + ": " + e.getMessage());
            }
        }
    }

    /**
     * Plan-Execute should honor max_tokens in generate blocks.
     *
     * <p>COUNTERFACTUAL: if gen.max_tokens is not read by the GraalJS plan compiler,
     * the LLM_CHAT_COMPLETE task gets the hardcoded default 4096. This test instructs
     * the planner to include max_tokens: 8192 in generate blocks and requests longer
     * sections (250+ words each). The field must be accepted without error.
     */
    @Test
    @Order(2)
    @Timeout(value = 300, unit = TimeUnit.SECONDS)
    void testMaxTokensInGenerate() {
        List<ToolDef> tools = List.of(
            createDirectoryTool(),
            writeFileTool(),
            readFileTool(),
            assembleFilesTool(),
            checkWordCountTool()
        );

        Agent planner = Agent.builder()
            .name("test_java_planner_maxtok")
            .model(MODEL)
            .instructions(MAX_TOKENS_PLANNER_INSTRUCTIONS)
            .maxTurns(3)
            .maxTokens(4000)
            .build();

        Agent fallback = Agent.builder()
            .name("test_java_fallback_maxtok")
            .model(MODEL)
            .instructions(FALLBACK_INSTRUCTIONS)
            .tools(tools)
            .maxTurns(10)
            .maxTokens(8000)
            .build();

        Agent harness = Agent.builder()
            .name("test_java_report_gen_maxtok")
            .model(MODEL)
            .agents(planner, fallback)
            .strategy(Strategy.PLAN_EXECUTE)
            .fallbackMaxTurns(5)
            .build();

        AgentResult result = runtime.run(harness,
            "Write a detailed research report about: Quantum computing applications in cryptography");

        // 1. Workflow completed — proves max_tokens field didn't break compilation
        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent did not complete. Status: " + result.getStatus()
            + ". Error: " + result.getError());

        // 2. Report file exists
        Path reportPath = WORK_DIR.resolve("report.md");
        assertTrue(Files.exists(reportPath),
            "Report file not found at " + reportPath);

        // 3. Report has substantial content
        String content;
        try {
            content = Files.readString(reportPath);
        } catch (IOException e) {
            fail("Failed to read report file: " + e.getMessage());
            return;
        }
        assertTrue(content.length() > 0, "Report file is empty");

        int wordCount = content.split("\\s+").length;

        // 4. Word count meets minimum
        assertTrue(wordCount >= MIN_WORD_COUNT,
            "Report has " + wordCount + " words, expected >= " + MIN_WORD_COUNT
            + ". COUNTERFACTUAL: if max_tokens was ignored, LLM output may be truncated.");

        // 5. Section files were created
        Path sectionsDir = WORK_DIR.resolve("sections");
        assertTrue(Files.isDirectory(sectionsDir), "sections/ directory not created");

        File[] sectionFiles = sectionsDir.toFile().listFiles(
            (dir, name) -> name.endsWith(".md"));
        assertNotNull(sectionFiles, "Could not list section files");
        assertTrue(sectionFiles.length >= 2,
            "Expected >= 2 section files, found " + sectionFiles.length);
    }
}
