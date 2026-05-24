// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentConfig;
import ai.agentspan.AgentRuntime;
import ai.agentspan.enums.AgentStatus;
import ai.agentspan.enums.Strategy;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.plans.Op;
import ai.agentspan.plans.Plan;
import ai.agentspan.plans.Ref;
import ai.agentspan.plans.Step;
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
class PlanExecuteTest extends BaseTest {

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
    @Timeout(value = 600, unit = TimeUnit.SECONDS)
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
            .tools(tools)
            .planner(planner)
            .fallback(fallback)
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
    @Timeout(value = 600, unit = TimeUnit.SECONDS)
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
            .tools(tools)
            .planner(planner)
            .fallback(fallback)
            .strategy(Strategy.PLAN_EXECUTE)
            .fallbackMaxTurns(5)
            .build();

        AgentResult result = runtime.run(harness,
            "Write a detailed research report about: Quantum computing applications in cryptography");

        // 1. Workflow completed — proves max_tokens field didn't break compilation
        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "Agent did not complete. Status: " + result.getStatus()
            + ". Error: " + result.getError());

        // 2. We used to assert ``report.md`` exists, but the planner LLM
        // names the final output file unpredictably across runs (report.txt,
        // research_report_*.txt, quantum_*.md, etc.) — the test was failing
        // not because max_tokens compilation broke but because the model
        // chose a different filename. The test's purpose is to verify the
        // compiler accepts ``max_tokens`` in generate blocks and the
        // resulting workflow runs end-to-end; any substantive text output
        // (>= MIN_WORD_COUNT across all produced text/markdown files
        // combined) satisfies that. Mirrors the TS equivalent in
        // tests/e2e/test_suite20_plan_execute.test.ts.
        List<Path> textFiles;
        try (var stream = Files.walk(WORK_DIR)) {
            textFiles = stream
                .filter(Files::isRegularFile)
                .filter(p -> {
                    String n = p.getFileName().toString();
                    return n.endsWith(".md") || n.endsWith(".txt");
                })
                .collect(java.util.stream.Collectors.toList());
        } catch (IOException e) {
            fail("Failed to walk WORK_DIR: " + e.getMessage());
            return;
        }

        StringBuilder all = new StringBuilder();
        for (Path p : textFiles) {
            try {
                all.append(Files.readString(p)).append("\n\n");
            } catch (IOException e) {
                fail("Failed to read " + p + ": " + e.getMessage());
                return;
            }
        }
        int wordCount = all.length() == 0 ? 0 : all.toString().trim().split("\\s+").length;
        System.err.println("[testMaxTokensInGenerate] produced " + textFiles.size()
            + " text file(s), total word count: " + wordCount
            + ", files=" + textFiles);

        // If the file-count assertion is about to fail, dump diagnostics
        // FIRST so the failure message tells us what actually happened —
        // not just "0 files produced." See dumpWorkflowDiagnostics for
        // the shape: status, reasonForIncompletion, planner output,
        // PAC's compile output (error/warnings/stats), which branch
        // fired, and tool task outcomes. This was added because CI was
        // failing intermittently with no actionable signal.
        if (textFiles.size() == 0 || wordCount < MIN_WORD_COUNT) {
            dumpWorkflowDiagnostics(result.getExecutionId(), "testMaxTokensInGenerate");
        }

        assertTrue(textFiles.size() > 0,
            "no .md/.txt files produced in " + WORK_DIR
            + ". COUNTERFACTUAL: if the GraalJS compiler dropped max_tokens, "
            + "the workflow may have terminated before writing any output."
            + " See stderr for workflow diagnostics.");
        assertTrue(wordCount >= MIN_WORD_COUNT,
            "Total word count " + wordCount + " < " + MIN_WORD_COUNT
            + ". COUNTERFACTUAL: if max_tokens was ignored, LLM output is truncated short."
            + " See stderr for workflow diagnostics.");
    }

    /**
     * Fetch the workflow with tasks and dump a debugging summary to stderr.
     * Used by tests whose assertions are several layers downstream from the
     * server-side behaviour they actually validate (e.g. file existence as
     * proxy for "planner emitted a plan that compiled and ran") — when those
     * fail the bare message is useless. This dumps the workflow's status,
     * each task's type/status/output, and recurses one level into
     * SUB_WORKFLOWs (the plan_exec sub-workflow is where the action is).
     *
     * <p>Best-effort: any network or JSON failure is caught and logged
     * rather than failing the test on top of the original failure.
     */
    @SuppressWarnings("unchecked")
    private void dumpWorkflowDiagnostics(String executionId, String label) {
        System.err.println();
        System.err.println("════════════════════════════════════════════════════");
        System.err.println("  [" + label + "] DIAGNOSTICS for execution " + executionId);
        System.err.println("════════════════════════════════════════════════════");
        try {
            Map<String, Object> wf = fetchWorkflowWithTasks(executionId);
            if (wf == null) {
                System.err.println("  (workflow fetch failed)");
                return;
            }
            System.err.println("  workflowName: " + wf.get("workflowName"));
            System.err.println("  status:       " + wf.get("status"));
            Object reason = wf.get("reasonForIncompletion");
            if (reason != null) {
                System.err.println("  reasonForIncompletion: " + truncate(reason.toString(), 500));
            }
            Object output = wf.get("output");
            if (output != null) {
                System.err.println("  parent output keys: "
                    + (output instanceof Map<?, ?> m ? m.keySet() : output.getClass().getSimpleName()));
            }
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) wf.getOrDefault("tasks", List.of());
            System.err.println("  task count: " + tasks.size());
            System.err.println();
            System.err.println("  PARENT TASKS:");
            String planExecSubId = null;
            String plannerSubId = null;
            for (Map<String, Object> t : tasks) {
                String ref = String.valueOf(t.getOrDefault("referenceTaskName", ""));
                String type = String.valueOf(t.getOrDefault("taskType", ""));
                String status = String.valueOf(t.getOrDefault("status", ""));
                System.err.printf("    %-12s %-18s %s%n", status, type, ref);

                // Capture sub-workflow IDs for nested dump.
                Object od = t.get("outputData");
                if (od instanceof Map<?, ?> odm) {
                    Object subId = odm.get("subWorkflowId");
                    if (subId instanceof String sid && !sid.isEmpty()) {
                        if (ref.endsWith("_plan_exec")) planExecSubId = sid;
                        else if (ref.endsWith("_planner")) plannerSubId = sid;
                    }
                }

                // For PLAN_AND_COMPILE: dump error + warnings + stats.
                if ("PLAN_AND_COMPILE".equals(type)) {
                    if (od instanceof Map<?, ?> odm) {
                        System.err.println("      error:    " + odm.get("error"));
                        System.err.println("      warnings: " + odm.get("warnings"));
                        System.err.println("      stats:    " + odm.get("stats"));
                    }
                }
                // For TERMINATE: dump reason.
                if ("TERMINATE".equals(type) && t.get("inputData") instanceof Map<?, ?> idm) {
                    System.err.println("      terminationReason: " + idm.get("terminationReason"));
                }
            }

            // Recurse into planner + plan_exec sub-workflows — that's where
            // the actual writes live.
            if (plannerSubId != null) {
                System.err.println();
                System.err.println("  PLANNER SUB-WORKFLOW (" + plannerSubId + "):");
                dumpChildWorkflow(plannerSubId, "    ");
            }
            if (planExecSubId != null) {
                System.err.println();
                System.err.println("  PLAN_EXEC SUB-WORKFLOW (" + planExecSubId + "):");
                dumpChildWorkflow(planExecSubId, "    ");
            }
            System.err.println("════════════════════════════════════════════════════");
            System.err.println();
        } catch (Exception e) {
            System.err.println("  (diagnostics dump failed: " + e.getMessage() + ")");
        }
    }

    /** Print one child workflow's tasks + status, indented by {@code indent}. */
    @SuppressWarnings("unchecked")
    private void dumpChildWorkflow(String executionId, String indent) {
        try {
            Map<String, Object> wf = fetchWorkflowWithTasks(executionId);
            if (wf == null) {
                System.err.println(indent + "(fetch failed)");
                return;
            }
            System.err.println(indent + "status: " + wf.get("status"));
            Object reason = wf.get("reasonForIncompletion");
            if (reason != null) {
                System.err.println(indent + "reasonForIncompletion: " + truncate(reason.toString(), 500));
            }
            List<Map<String, Object>> tasks = (List<Map<String, Object>>) wf.getOrDefault("tasks", List.of());
            for (Map<String, Object> t : tasks) {
                String ref = String.valueOf(t.getOrDefault("referenceTaskName", ""));
                String type = String.valueOf(t.getOrDefault("taskType", ""));
                String status = String.valueOf(t.getOrDefault("status", ""));
                String defName = String.valueOf(t.getOrDefault("taskDefName", ""));
                System.err.printf(indent + "%-12s %-18s %-40s def=%s%n", status, type, ref, defName);
                // For user-tool SIMPLE tasks, surface input + output briefly.
                if ("SIMPLE".equals(type)) {
                    Object id = t.get("inputData");
                    Object od = t.get("outputData");
                    System.err.println(indent + "  input:  " + truncate(String.valueOf(id), 200));
                    System.err.println(indent + "  output: " + truncate(String.valueOf(od), 200));
                }
                if ("LLM_CHAT_COMPLETE".equals(type)) {
                    Object od = t.get("outputData");
                    if (od instanceof Map<?, ?> odm) {
                        Object r = odm.get("result");
                        System.err.println(indent + "  llm output: " + truncate(String.valueOf(r), 300));
                    }
                }
            }
        } catch (Exception e) {
            System.err.println(indent + "(child dump failed: " + e.getMessage() + ")");
        }
    }

    /** Fetch a workflow with includeTasks=true (the base class helper omits the flag). */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> fetchWorkflowWithTasks(String executionId) {
        try {
            java.net.http.HttpClient http = java.net.http.HttpClient.newBuilder()
                .connectTimeout(java.time.Duration.ofSeconds(10))
                .build();
            java.net.http.HttpRequest req = java.net.http.HttpRequest.newBuilder()
                .uri(java.net.URI.create(BASE_URL + "/api/workflow/" + executionId + "?includeTasks=true"))
                .timeout(java.time.Duration.ofSeconds(10))
                .GET()
                .build();
            java.net.http.HttpResponse<String> resp = http.send(req,
                java.net.http.HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() >= 400) return null;
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(resp.body(), Map.class);
        } catch (Exception e) {
            return null;
        }
    }

    private static String truncate(String s, int max) {
        if (s == null) return "null";
        return s.length() <= max ? s : s.substring(0, max) + "…(" + (s.length() - max) + " more chars)";
    }

    // ── Deterministic PAC/PAE tests — no LLM in assertion path ──────────
    //
    // The planner sub-agent is built but its output is discarded by the
    // static-plan path (`runtime.run(harness, prompt, plan)`). All
    // assertions are algorithmic — per CLAUDE.md, we never use LLM output
    // for validation.

    static ToolDef jProduceTool() {
        return ToolDef.builder()
            .name("j_s20_produce")
            .description("Step A — emit a known record.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of("record_id", Map.of("type", "string")),
                "required", List.of("record_id")))
            .toolType("worker")
            .func(input -> Map.of(
                "record_id", input.get("record_id"),
                "value", 42,
                "tags", List.of("alpha", "beta")))
            .build();
    }

    static ToolDef jEnrichTool() {
        return ToolDef.builder()
            .name("j_s20_enrich")
            .description("Step B — read Step A via Ref.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of("record", Map.of("type", "object")),
                "required", List.of("record")))
            .toolType("worker")
            .func(input -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> record = (Map<String, Object>) input.get("record");
                Map<String, Object> out = new LinkedHashMap<>(record);
                int value = ((Number) record.getOrDefault("value", 0)).intValue();
                out.put("value_squared", value * value);
                return out;
            })
            .build();
    }

    static ToolDef jReportTool() {
        return ToolDef.builder()
            .name("j_s20_report")
            .description("Step C — read BOTH upstream steps.")
            .inputSchema(Map.of(
                "type", "object",
                "properties", Map.of(
                    "record", Map.of("type", "object"),
                    "enriched", Map.of("type", "object")),
                "required", List.of("record", "enriched")))
            .toolType("worker")
            .func(input -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> record = (Map<String, Object>) input.get("record");
                @SuppressWarnings("unchecked")
                Map<String, Object> enriched = (Map<String, Object>) input.get("enriched");
                @SuppressWarnings("unchecked")
                List<Object> tags = (List<Object>) record.get("tags");
                Map<String, Object> out = new LinkedHashMap<>();
                out.put("id", record.get("record_id"));
                out.put("original_value", record.get("value"));
                out.put("squared", enriched.get("value_squared"));
                out.put("tags_joined", String.join(
                    ", ", tags.stream().map(Object::toString).toList()));
                return out;
            })
            .build();
    }

    Agent buildRefsHarness() {
        Agent planner = Agent.builder()
            .name("j_s20_refs_planner")
            .model(MODEL)
            .instructions("(planner unused; static plan supplied)")
            .build();
        return Agent.builder()
            .name("j_s20_refs_harness")
            .model(MODEL)
            .strategy(Strategy.PLAN_EXECUTE)
            .planner(planner)
            .tools(List.of(jProduceTool(), jEnrichTool(), jReportTool()))
            .build();
    }

    @SuppressWarnings("unchecked")
    Map<String, Map<String, Object>> fetchStepOutputs(String executionId) throws Exception {
        Map<String, Object> parent = getWorkflow(executionId);
        String subId = null;
        for (Map<String, Object> t : (List<Map<String, Object>>) parent.getOrDefault("tasks", List.of())) {
            String ref = String.valueOf(t.getOrDefault("referenceTaskName", ""));
            if (ref.endsWith("_plan_exec")) {
                Map<String, Object> out = (Map<String, Object>) t.get("outputData");
                subId = out == null ? null : (String) out.get("subWorkflowId");
                break;
            }
        }
        if (subId == null) return Map.of();
        Map<String, Object> sub = getWorkflow(subId);
        Map<String, Map<String, Object>> result = new LinkedHashMap<>();
        for (Map<String, Object> t : (List<Map<String, Object>>) sub.getOrDefault("tasks", List.of())) {
            String name = String.valueOf(t.get("taskDefName"));
            if (name.startsWith("j_s20_")) {
                result.put(name, (Map<String, Object>) t.get("outputData"));
            }
        }
        return result;
    }

    /**
     * Counterfactual: if the SDK didn't rewrite {@code {"$ref":"a"}} to a
     * Conductor template, step B would receive the literal marker dict and
     * value_squared would be 0 (not 1764). Asserting the exact squared
     * value rules that out.
     */
    @Test
    @Order(10)
    @Timeout(value = 600, unit = TimeUnit.SECONDS)
    void testRefPipesWholeOutputAcrossSteps() throws Exception {
        Agent harness = buildRefsHarness();
        Plan plan = Plan.builder()
            .step(Step.builder("a")
                .operation(Op.builder("j_s20_produce")
                    .args(Map.of("record_id", "r-001"))
                    .build())
                .build())
            .step(Step.builder("b")
                .dependsOn("a")
                .operation(Op.builder("j_s20_enrich")
                    .args(Map.of("record", new Ref("a")))
                    .build())
                .build())
            .build();

        AgentResult result = runtime.run(harness, "go", plan);
        assertEquals(AgentStatus.COMPLETED, result.getStatus(),
            "workflow did not COMPLETE: status=" + result.getStatus() + " error=" + result.getError());

        Map<String, Map<String, Object>> outputs = fetchStepOutputs(result.getExecutionId());

        Map<String, Object> produce = outputs.get("j_s20_produce");
        assertNotNull(produce, "produce step did not run");
        assertEquals("r-001", produce.get("record_id"));
        assertEquals(42, ((Number) produce.get("value")).intValue());

        Map<String, Object> enrich = outputs.get("j_s20_enrich");
        assertNotNull(enrich, "enrich step did not run — Ref likely unwired");
        assertEquals(
            1764, ((Number) enrich.get("value_squared")).intValue(),
            "value_squared must be 1764 (= 42²). If Ref didn't carry the dict, "
            + "enrich would have received the literal {\"$ref\":\"a\"} marker and squared 0. "
            + "Full enrich output: " + enrich);
        assertEquals("r-001", enrich.get("record_id"));
        assertEquals(42, ((Number) enrich.get("value")).intValue());
    }

    /**
     * Two Refs in the same {@code args} map must resolve independently —
     * one to step A's output, the other to step B's. Counterfactual: if
     * the recursive serializer collapsed both, squared would equal
     * original_value (42); asserting squared=1764 ≠ original_value=42
     * rules it out.
     */
    @Test
    @Order(11)
    @Timeout(value = 600, unit = TimeUnit.SECONDS)
    void testTwoRefsInSameArgsResolveIndependently() throws Exception {
        Agent harness = buildRefsHarness();
        Plan plan = Plan.builder()
            .step(Step.builder("a")
                .operation(Op.builder("j_s20_produce")
                    .args(Map.of("record_id", "r-001"))
                    .build())
                .build())
            .step(Step.builder("b")
                .dependsOn("a")
                .operation(Op.builder("j_s20_enrich")
                    .args(Map.of("record", new Ref("a")))
                    .build())
                .build())
            .step(Step.builder("c")
                .dependsOn("a", "b")
                .operation(Op.builder("j_s20_report")
                    .args(Map.of(
                        "record", new Ref("a"),
                        "enriched", new Ref("b")))
                    .build())
                .build())
            .build();

        AgentResult result = runtime.run(harness, "go", plan);
        assertEquals(AgentStatus.COMPLETED, result.getStatus());

        Map<String, Map<String, Object>> outputs = fetchStepOutputs(result.getExecutionId());
        Map<String, Object> report = outputs.get("j_s20_report");
        assertNotNull(report, "report step did not run");
        assertEquals("r-001", report.get("id"));
        assertEquals(42, ((Number) report.get("original_value")).intValue());
        assertEquals(1764, ((Number) report.get("squared")).intValue());
        assertEquals("alpha, beta", report.get("tags_joined"));
    }
}
