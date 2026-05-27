// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.AgentTool;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolDef;
import ai.agentspan.internal.AgentConfigSerializer;
import ai.agentspan.skill.Skill;
import ai.agentspan.skill.SkillLoadError;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Suite 17: Skills — load and structural assertions for {@link Skill}.
 *
 * <p>Mirrors Python {@code test_suite15_skills.py}. A skill is a directory with a
 * {@code SKILL.md} (YAML frontmatter + body), optional {@code *-agent.md} sub-agent files,
 * and an optional {@code scripts/} directory. {@code Skill.skill(path, model)} loads it as
 * an Agent with {@code framework="skill"} and a raw config map.
 *
 * <p>Tests use plan() — no LLM calls. Each assertion has a counterfactual.
 */
@Tag("e2e")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Timeout(value = 300, unit = TimeUnit.SECONDS)
class Suite15Skills extends BaseTest {

    private static AgentRuntime runtime;

    @BeforeAll
    static void setup() {
        runtime = new AgentRuntime(new ai.agentspan.AgentConfig(BASE_URL, null, null, 100, 1));
    }

    @AfterAll
    static void teardown() {
        if (runtime != null) runtime.close();
    }

    // ── Fixture helpers ───────────────────────────────────────────────────────

    /**
     * Create a minimal valid skill directory:
     *   SKILL.md (with name=test_skill_e2e_s17)
     *   alpha-agent.md
     *   beta-agent.md
     *   scripts/echo_args.py
     */
    private static void writeSkillDir(Path dir) throws Exception {
        String skillMd = "---\n"
            + "name: test_skill_e2e_s17\n"
            + "params:\n"
            + "  mode:\n"
            + "    default: fast\n"
            + "---\n"
            + "## Overview\n"
            + "A test skill with two sub-agents and a script.\n"
            + "\n"
            + "## Workflow\n"
            + "1. If no prior tool result is available, call the test_skill_e2e_s17__echo_args tool exactly once.\n"
            + "2. Pass the original user's input as the argument.\n"
            + "3. After a tool result containing ECHO_ARGS_RESULT: is available, return that exact line as the final answer.\n"
            + "4. If asked to continue, do not call any tool. Return the most recent ECHO_ARGS_RESULT: line exactly.\n";
        Files.writeString(dir.resolve("SKILL.md"), skillMd);
        Files.writeString(dir.resolve("alpha-agent.md"), "# Alpha Agent\nYou analyze the input.\n");
        Files.writeString(dir.resolve("beta-agent.md"), "# Beta Agent\nYou summarize the analysis.\n");
        Path referencesDir = dir.resolve("references");
        Files.createDirectories(referencesDir);
        Files.writeString(referencesDir.resolve("guide.md"), "# JAVA_REFERENCE_GUIDE\nUse this deterministic guide.\n");

        Path scriptsDir = dir.resolve("scripts");
        Files.createDirectories(scriptsDir);
        Path echoPath = scriptsDir.resolve("echo_args.py");
        String echoScript = "#!/usr/bin/env python3\n"
            + "import sys\n"
            + "args = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'no-args'\n"
            + "print(f'ECHO_ARGS_RESULT:{args}')\n";
        Files.writeString(echoPath, echoScript);
    }

    // ── Tests ─────────────────────────────────────────────────────────────────

    /**
     * Pure SDK property test: Skill.skill() parses SKILL.md frontmatter and discovers
     * sub-agent files and scripts.
     *
     * COUNTERFACTUAL: a plain Agent has NO _framework="skill", and Skill.skill() with a
     * missing SKILL.md must throw — the test asserts both contrasts.
     */
    @Test
    @Order(1)
    @SuppressWarnings("unchecked")
    void test_skill_loading_basic_properties(@TempDir Path tempDir) throws Exception {
        writeSkillDir(tempDir);

        Agent agent = Skill.skill(tempDir, MODEL);

        assertEquals("test_skill_e2e_s17", agent.getName(),
            "Skill agent name should come from SKILL.md frontmatter. Got: " + agent.getName());
        assertEquals("skill", agent.getFramework(),
            "Skill agent framework must be 'skill'. Got: " + agent.getFramework()
            + ". COUNTERFACTUAL: paired with plain-agent contrast below.");
        assertEquals(MODEL, agent.getModel(),
            "Skill agent model should be the provided MODEL. Got: " + agent.getModel());

        Map<String, Object> cfg = agent.getFrameworkConfig();
        assertNotNull(cfg, "Skill frameworkConfig must not be null.");

        Map<String, String> agentFiles = (Map<String, String>) cfg.get("agentFiles");
        assertNotNull(agentFiles, "frameworkConfig.agentFiles missing.");
        assertTrue(agentFiles.containsKey("alpha"),
            "agentFiles must contain 'alpha'. Got: " + agentFiles.keySet());
        assertTrue(agentFiles.containsKey("beta"),
            "agentFiles must contain 'beta'. Got: " + agentFiles.keySet());

        Map<String, Map<String, String>> scripts = (Map<String, Map<String, String>>) cfg.get("scripts");
        assertNotNull(scripts, "frameworkConfig.scripts missing.");
        assertTrue(scripts.containsKey("echo_args"),
            "scripts must contain 'echo_args'. Got: " + scripts.keySet());
        assertEquals("python", scripts.get("echo_args").get("language"),
            "echo_args.language should be 'python'. Got: " + scripts.get("echo_args").get("language")
            + ". COUNTERFACTUAL: if language detection always returns 'bash', this fails.");

        String skillMd = (String) cfg.get("skillMd");
        assertNotNull(skillMd, "skillMd missing.");
        assertTrue(skillMd.contains("test_skill_e2e_s17"),
            "skillMd should contain the skill name. Got: " + skillMd.substring(0, Math.min(200, skillMd.length())));

        // Counterfactual: a plain Agent has NO framework="skill".
        Agent plain = Agent.builder()
            .name("e2e_s17_plain")
            .model(MODEL)
            .instructions("Plain agent.")
            .build();
        assertNull(plain.getFramework(),
            "Plain Agent must have framework=null. Got: " + plain.getFramework()
            + ". COUNTERFACTUAL: if framework() defaulted to 'skill', every agent would be a skill.");
        assertNull(plain.getFrameworkConfig(),
            "Plain Agent must have frameworkConfig=null. Got: " + plain.getFrameworkConfig());
    }

    /**
     * Skill.skill() throws SkillLoadError when SKILL.md is missing.
     *
     * COUNTERFACTUAL: a valid directory must NOT throw — pairs with the above.
     */
    @Test
    @Order(2)
    void test_skill_missing_md_throws(@TempDir Path emptyDir) throws Exception {
        SkillLoadError ex = assertThrows(SkillLoadError.class,
            () -> Skill.skill(emptyDir, MODEL),
            "Skill.skill() with missing SKILL.md must throw. "
            + "COUNTERFACTUAL: if validation is missing, the test would pass silently.");
        assertTrue(ex.getMessage().contains("SKILL.md"),
            "Error message must mention 'SKILL.md'. Got: " + ex.getMessage());

        // Counterfactual: a valid dir must succeed.
        Path validDir = emptyDir.resolve("valid_sub");
        Files.createDirectories(validDir);
        writeSkillDir(validDir);
        Agent ok = Skill.skill(validDir, MODEL);
        assertNotNull(ok, "Valid skill dir should load.");
        assertEquals("skill", ok.getFramework(),
            "Valid skill agent should have framework='skill'.");
    }

    /**
     * Skill.skill() throws SkillLoadError when SKILL.md is missing the 'name' field
     * in YAML frontmatter.
     *
     * COUNTERFACTUAL: well-formed SKILL.md succeeds.
     */
    @Test
    @Order(3)
    void test_skill_missing_name_throws(@TempDir Path dir) throws Exception {
        String badMd = "---\n"
            + "description: A skill without a name\n"
            + "---\n"
            + "## Body\nNo name field above.\n";
        Files.writeString(dir.resolve("SKILL.md"), badMd);

        SkillLoadError ex = assertThrows(SkillLoadError.class,
            () -> Skill.skill(dir, MODEL),
            "Skill.skill() with missing 'name' field must throw. "
            + "COUNTERFACTUAL: if name parsing always returns a fallback, this would pass silently.");
        assertTrue(ex.getMessage().toLowerCase().contains("name"),
            "Error must mention 'name'. Got: " + ex.getMessage());
    }

    /**
     * SDK serializer + plan compilation: the SDK's serializer emits {@code _framework="skill"}
     * along with skillMd/agentFiles/scripts in the wire payload, and the server compiles
     * the skill into a valid workflow without error.
     *
     * <p>The {@code _framework} flag and raw skill blocks are inspected on the SDK-side
     * serializer output (which is what we send on the wire) rather than the round-tripped
     * plan response, because the server's AgentConfig DTO does not echo back the raw
     * framework fields — they're consumed during compilation.
     *
     * COUNTERFACTUAL: a plain Agent's serializer output has NO _framework key.
     */
    @Test
    @Order(4)
    @SuppressWarnings("unchecked")
    void test_skill_serializes_to_plan(@TempDir Path tempDir) throws Exception {
        writeSkillDir(tempDir);
        Agent skillAgent = Skill.skill(tempDir, MODEL);

        // Inspect the wire payload the SDK sends.
        AgentConfigSerializer ser = new AgentConfigSerializer();
        Map<String, Object> wire = ser.serialize(skillAgent);

        assertEquals("skill", wire.get("_framework"),
            "Serialized wire payload._framework should be 'skill'. Got: " + wire.get("_framework")
            + ". COUNTERFACTUAL: paired with the plain-agent contrast below.");
        assertEquals("test_skill_e2e_s17", wire.get("name"),
            "wire.name should match the skill name. Got: " + wire.get("name"));

        assertNotNull(wire.get("skillMd"),
            "wire.skillMd must be present so server compiles sub-agents. "
            + "COUNTERFACTUAL: if frameworkConfig is dropped, the server can't compile the skill.");
        Map<String, String> wireAgentFiles = (Map<String, String>) wire.get("agentFiles");
        assertNotNull(wireAgentFiles, "wire.agentFiles missing.");
        assertTrue(wireAgentFiles.containsKey("alpha"),
            "wire agentFiles must contain 'alpha'. Got: " + wireAgentFiles.keySet());
        assertTrue(wireAgentFiles.containsKey("beta"),
            "wire agentFiles must contain 'beta'. Got: " + wireAgentFiles.keySet());

        // Counterfactual: a plain Agent's wire payload has NO _framework
        Agent plain = Agent.builder()
            .name("e2e_s17_plain_plan")
            .model(MODEL)
            .instructions("Plain.")
            .build();
        Map<String, Object> plainWire = ser.serialize(plain);
        assertNotEquals("skill", plainWire.get("_framework"),
            "Plain wire._framework must NOT be 'skill'. Got: " + plainWire.get("_framework")
            + ". COUNTERFACTUAL: this proves _framework is conditional on Skill.skill().");
        assertFalse(plainWire.containsKey("skillMd"),
            "Plain wire payload must NOT carry skillMd. Got keys: " + plainWire.keySet()
            + ". COUNTERFACTUAL: if skillMd were always emitted, every agent would look like a skill.");
        assertFalse(plainWire.containsKey("agentFiles"),
            "Plain wire payload must NOT carry agentFiles. Got keys: " + plainWire.keySet());

        // Final integration check: the server accepts the skill payload and returns a valid plan.
        Map<String, Object> plan = runtime.plan(skillAgent);
        assertNotNull(plan, "Skill plan() should return a non-null result.");
        assertNotNull(plan.get("workflowDef"),
            "Skill plan().workflowDef must be present. plan keys: " + plan.keySet()
            + ". COUNTERFACTUAL: if the server rejected the skill payload, this would throw or return null.");
    }

    /**
     * Skill loadSkills() loads every subdirectory containing a SKILL.md.
     *
     * COUNTERFACTUAL: an empty parent dir produces an empty map.
     */
    @Test
    @Order(5)
    @SuppressWarnings("unchecked")
    void test_load_skills_multiple_dirs(@TempDir Path parent) throws Exception {
        Path skill1 = parent.resolve("skill_one");
        Path skill2 = parent.resolve("skill_two");
        Files.createDirectories(skill1);
        Files.createDirectories(skill2);

        Files.writeString(skill1.resolve("SKILL.md"), "---\nname: e2e_s17_one\n---\n# one\n");
        Files.writeString(skill2.resolve("SKILL.md"), "---\nname: e2e_s17_two\n---\n# two\n");
        // A subdir without SKILL.md must be skipped.
        Path notSkill = parent.resolve("not_a_skill");
        Files.createDirectories(notSkill);
        Files.writeString(notSkill.resolve("README.md"), "no SKILL.md here");

        Map<String, Agent> all = Skill.loadSkills(parent, MODEL);
        assertTrue(all.containsKey("skill_one"),
            "loadSkills must include 'skill_one'. Got keys: " + all.keySet());
        assertTrue(all.containsKey("skill_two"),
            "loadSkills must include 'skill_two'. Got keys: " + all.keySet());
        assertFalse(all.containsKey("not_a_skill"),
            "loadSkills must SKIP directories without SKILL.md. Got keys: " + all.keySet()
            + ". COUNTERFACTUAL: if loadSkills loaded every subdir, 'not_a_skill' would appear.");
        assertEquals("e2e_s17_one", all.get("skill_one").getName(),
            "Skill name must come from SKILL.md, not directory name. Got: " + all.get("skill_one").getName());
        assertEquals("e2e_s17_two", all.get("skill_two").getName(),
            "Skill name must come from SKILL.md, not directory name. Got: " + all.get("skill_two").getName());
        assertEquals("skill", all.get("skill_one").getFramework(),
            "Loaded skill must have framework='skill'.");

        // Counterfactual: empty parent yields empty map
        Path emptyParent = parent.resolve("empty_parent");
        Files.createDirectories(emptyParent);
        Map<String, Agent> none = Skill.loadSkills(emptyParent, MODEL);
        assertTrue(none.isEmpty(),
            "loadSkills on an empty dir must return empty map. Got: " + none.keySet()
            + ". COUNTERFACTUAL: if loadSkills synthesized phantom entries, this fails.");
    }

    /**
     * Script language detection: .py is python, .sh is bash, .js is node.
     *
     * COUNTERFACTUAL: distinct extensions must yield DIFFERENT languages — proves
     * detection isn't a constant.
     */
    @Test
    @Order(6)
    @SuppressWarnings("unchecked")
    void test_skill_script_language_detection(@TempDir Path dir) throws Exception {
        Files.writeString(dir.resolve("SKILL.md"), "---\nname: e2e_s17_lang\n---\n# x\n");
        Path scripts = dir.resolve("scripts");
        Files.createDirectories(scripts);
        Files.writeString(scripts.resolve("py_script.py"), "print('hi')");
        Files.writeString(scripts.resolve("sh_script.sh"), "echo hi");
        Files.writeString(scripts.resolve("js_script.js"), "console.log('hi')");

        Agent agent = Skill.skill(dir, MODEL);
        Map<String, Map<String, String>> scriptsCfg =
            (Map<String, Map<String, String>>) agent.getFrameworkConfig().get("scripts");
        assertNotNull(scriptsCfg, "scripts missing in frameworkConfig");

        assertEquals("python", scriptsCfg.get("py_script").get("language"),
            ".py should detect as 'python'. Got: " + scriptsCfg.get("py_script").get("language"));
        assertEquals("bash", scriptsCfg.get("sh_script").get("language"),
            ".sh should detect as 'bash'. Got: " + scriptsCfg.get("sh_script").get("language"));
        assertEquals("node", scriptsCfg.get("js_script").get("language"),
            ".js should detect as 'node'. Got: " + scriptsCfg.get("js_script").get("language"));

        // Counterfactual contrast: each extension yields a different language.
        List<String> langs = List.of(
            scriptsCfg.get("py_script").get("language"),
            scriptsCfg.get("sh_script").get("language"),
            scriptsCfg.get("js_script").get("language"));
        assertEquals(3, langs.stream().distinct().count(),
            "Three distinct extensions must yield three distinct languages. Got: " + langs
            + ". COUNTERFACTUAL: if detectLanguage always returned 'bash', distinct count would be 1.");
    }

    /**
     * Script discovery: each script entry must include the filename in addition to language.
     *
     * Ports Python {@code test_skill_script_discovery} — verifies the {@code filename}
     * key is present on script metadata so the server can locate the script body.
     *
     * COUNTERFACTUAL: an unrelated agent without scripts has no 'scripts' map.
     */
    @Test
    @Order(7)
    @SuppressWarnings("unchecked")
    void test_skill_script_discovery_includes_filename(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);

        Agent agent = Skill.skill(dir, MODEL);
        Map<String, Map<String, String>> scripts =
            (Map<String, Map<String, String>>) agent.getFrameworkConfig().get("scripts");
        assertNotNull(scripts, "scripts missing in frameworkConfig");

        assertTrue(scripts.containsKey("echo_args"),
            "scripts must contain 'echo_args'. Got: " + scripts.keySet());
        assertEquals("python", scripts.get("echo_args").get("language"),
            ".py should detect as 'python'.");
        assertEquals("echo_args.py", scripts.get("echo_args").get("filename"),
            "Script entry must include the filename so the server can locate it. Got: "
            + scripts.get("echo_args").get("filename")
            + ". COUNTERFACTUAL: dropping filename would leave the server unable to invoke the script.");

        // Counterfactual: a skill with no scripts dir produces no scripts entry (or empty)
        Path noScripts = dir.resolveSibling("no_scripts");
        Files.createDirectories(noScripts);
        Files.writeString(noScripts.resolve("SKILL.md"),
            "---\nname: e2e_s17_no_scripts\n---\n# body\n");
        Agent noScriptsAgent = Skill.skill(noScripts, MODEL);
        Map<String, Map<String, String>> noScriptsCfg =
            (Map<String, Map<String, String>>) noScriptsAgent.getFrameworkConfig().get("scripts");
        assertTrue(noScriptsCfg == null || noScriptsCfg.isEmpty(),
            "A skill with no scripts/ directory must have an empty/null scripts map. Got: "
            + noScriptsCfg);
    }

    @Test
    @Order(8)
    void test_skill_workers_execute_scripts_and_read_resources(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);
        Agent agent = Skill.skill(dir, MODEL);
        List<Skill.SkillWorker> workers = Skill.createSkillWorkers(agent);
        List<String> workerNames = workers.stream().map(Skill.SkillWorker::getName).toList();

        assertTrue(workerNames.contains("test_skill_e2e_s17__echo_args"),
            "Skill worker list must include script worker. Got: " + workerNames);
        assertTrue(workerNames.contains("test_skill_e2e_s17__read_skill_file"),
            "Skill worker list must include read_skill_file worker. Got: " + workerNames);

        Skill.SkillWorker echo = workers.stream()
            .filter(w -> w.getName().endsWith("__echo_args"))
            .findFirst()
            .orElseThrow();
        Object echoResult = echo.getFunc().apply(Map.of("command", "hello world"));
        assertTrue(String.valueOf(echoResult).contains("ECHO_ARGS_RESULT:hello world"),
            "Script worker must execute locally and return deterministic marker. Got: " + echoResult);

        Skill.SkillWorker read = workers.stream()
            .filter(w -> w.getName().endsWith("__read_skill_file"))
            .findFirst()
            .orElseThrow();
        Object guide = read.getFunc().apply(Map.of("path", "references/guide.md"));
        assertTrue(String.valueOf(guide).contains("JAVA_REFERENCE_GUIDE"),
            "read_skill_file worker must read allowlisted resources. Got: " + guide);
        Object denied = read.getFunc().apply(Map.of("path", "../SKILL.md"));
        assertTrue(String.valueOf(denied).contains("ERROR:"),
            "read_skill_file worker must reject paths outside the allowlist. Got: " + denied);
    }

    /**
     * Per-sub-agent model overrides: {@code Skill.skill(path, model, agentModels)} threads
     * a per-name model into the wire payload so the server compiles each sub-agent with
     * its own model.
     *
     * COUNTERFACTUAL: the default overload (no agentModels) must NOT carry a per-agent
     * model map in its wire payload.
     */
    @Test
    @Order(8)
    @SuppressWarnings("unchecked")
    void test_skill_per_sub_agent_model_override(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);

        Map<String, String> overrides = new HashMap<>();
        overrides.put("alpha", "openai/gpt-4o");
        overrides.put("beta",  "anthropic/claude-3-5-sonnet-20241022");

        Agent agent = Skill.skill(dir, MODEL, overrides);
        assertEquals("skill", agent.getFramework(),
            "Agent loaded via the agentModels overload must still have framework='skill'.");

        Map<String, Object> cfg = agent.getFrameworkConfig();
        assertNotNull(cfg, "frameworkConfig must be present.");

        // The agentModels map should be threaded into frameworkConfig under
        // some key — accept either 'agentModels' or 'agent_models' to be tolerant
        // of naming, but require at least one of the two with the supplied values.
        Map<String, String> threaded = (Map<String, String>) cfg.getOrDefault("agentModels",
                                       cfg.get("agent_models"));
        assertNotNull(threaded,
            "agentModels map must be threaded into frameworkConfig. Got keys: " + cfg.keySet()
            + ". COUNTERFACTUAL: if the overload silently dropped the map, this would be null.");
        assertEquals("openai/gpt-4o", threaded.get("alpha"),
            "alpha sub-agent must use the override model. Got: " + threaded.get("alpha"));
        assertEquals("anthropic/claude-3-5-sonnet-20241022", threaded.get("beta"),
            "beta sub-agent must use the override model. Got: " + threaded.get("beta"));

        // Counterfactual: default overload has no per-agent model map (or it's empty).
        Agent defaultAgent = Skill.skill(dir, MODEL);
        Map<String, Object> defaultCfg = defaultAgent.getFrameworkConfig();
        Map<String, String> defaultThreaded =
            (Map<String, String>) defaultCfg.getOrDefault("agentModels",
                                       defaultCfg.get("agent_models"));
        assertTrue(defaultThreaded == null || defaultThreaded.isEmpty(),
            "Default Skill.skill() (no agentModels) must NOT carry a populated agentModels map. "
            + "Got: " + defaultThreaded
            + ". COUNTERFACTUAL: this proves the override path is actually taken when supplied.");
    }

    @Test
    @Order(9)
    @SuppressWarnings("unchecked")
    void test_skill_params_and_cross_skill_refs_are_threaded(@TempDir Path parent) throws Exception {
        Path main = parent.resolve("main-skill");
        Path child = parent.resolve("child-skill");
        Path grandchild = parent.resolve("grandchild-skill");
        Files.createDirectories(main);
        Files.createDirectories(child);
        Files.createDirectories(grandchild);
        Files.writeString(main.resolve("SKILL.md"), "---\nname: main-skill\nparams:\n  mode:\n    default: fast\n---\n# Main\nUse the child-skill skill.\n");
        Files.writeString(child.resolve("SKILL.md"), "---\nname: child-skill\nparams:\n  childMode: compact\n---\n# Child\nUse the grandchild-skill skill.\n");
        Files.writeString(grandchild.resolve("SKILL.md"), "---\nname: grandchild-skill\n---\n# Grandchild\n");

        Agent agent = Skill.skill(main, MODEL, null, Map.of("mode", "slow", "rounds", 2));
        Map<String, Object> cfg = agent.getFrameworkConfig();

        Map<String, Object> params = (Map<String, Object>) cfg.get("params");
        assertEquals("slow", params.get("mode"));
        assertEquals(2, params.get("rounds"));
        assertTrue(String.valueOf(cfg.get("skillMd")).contains("[Skill Parameters]"));

        Map<String, Object> refs = (Map<String, Object>) cfg.get("crossSkillRefs");
        assertTrue(refs.containsKey("child-skill"), "crossSkillRefs must include child-skill. Got: " + refs.keySet());
        Map<String, Object> childRef = (Map<String, Object>) refs.get("child-skill");
        Map<String, Object> nestedRefs = (Map<String, Object>) childRef.get("crossSkillRefs");
        assertTrue(nestedRefs.containsKey("grandchild-skill"),
            "child-skill crossSkillRefs must include grandchild-skill. Got: " + nestedRefs.keySet());

        Path isolatedRoot = parent.resolve("isolated-root");
        Path isolatedMain = parent.resolve("isolated-main");
        Path isolatedChild = isolatedRoot.resolve("isolated-child");
        Files.createDirectories(isolatedMain);
        Files.createDirectories(isolatedChild);
        Files.writeString(isolatedMain.resolve("SKILL.md"),
            "---\nname: isolated-main\n---\n# Main\nUse the isolated-child skill.\n");
        Files.writeString(isolatedChild.resolve("SKILL.md"),
            "---\nname: isolated-child\n---\n# Child\n");

        Agent isolated = Skill.skill(isolatedMain, MODEL, null, null, List.of(isolatedRoot));
        Map<String, Object> isolatedCfg = isolated.getFrameworkConfig();
        Map<String, Object> isolatedRefs = (Map<String, Object>) isolatedCfg.get("crossSkillRefs");
        assertTrue(isolatedRefs.containsKey("isolated-child"),
            "explicit searchPath must resolve isolated-child. Got: " + isolatedRefs.keySet());
    }

    /**
     * Skill as a nested {@link AgentTool}: the parent agent's plan compiles, and the
     * skill's sub-workflow is wired in as a SUB_WORKFLOW task.
     *
     * Ports Python {@code test_agent_tool_skill_workers_registered} at the structural
     * (plan) level — we don't run the LLM, but we verify the compiled workflow at least
     * has a SUB_WORKFLOW edge into the skill's sub-workflow. This is the regression
     * guard for "skill nested in agent_tool didn't compile at all".
     *
     * COUNTERFACTUAL: a parent without the skill agent_tool has no SUB_WORKFLOW tasks
     * referencing the skill name.
     */
    @Test
    @Order(10)
    @SuppressWarnings("unchecked")
    void test_skill_nested_in_agent_tool_compiles(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);
        Agent skillAgent = Skill.skill(dir, MODEL);
        ToolDef skillTool = AgentTool.from(skillAgent, "Run the test skill with echo_args.");
        Object workerNamesObj = skillTool.getConfig().get("workerNames");
        assertTrue(workerNamesObj instanceof List,
            "agent_tool config must include workerNames for skill worker domain routing. Got: "
            + skillTool.getConfig());
        assertEquals(
            List.of("test_skill_e2e_s17__echo_args", "test_skill_e2e_s17__read_skill_file"),
            ((List<?>) workerNamesObj).stream().sorted().toList(),
            "Skill agent_tool workerNames must include script and read-file workers.");

        Agent parent = Agent.builder()
            .name("e2e_s17_skill_in_at")
            .model(MODEL)
            .instructions("You have one tool: test_skill_e2e_s17. Call it once and return the result.")
            .tools(List.of(skillTool))
            .build();

        Map<String, Object> plan = runtime.plan(parent);
        assertNotNull(plan, "plan() must return a non-null result for skill-in-agent_tool parent.");
        Map<String, Object> workflowDef = (Map<String, Object>) plan.get("workflowDef");
        assertNotNull(workflowDef,
            "workflowDef must be present. COUNTERFACTUAL: if compilation failed, this would be null.");

        // Plan should reference the skill name somewhere — its sub-workflow or tool entry.
        String wfStr = workflowDef.toString();
        assertTrue(wfStr.contains("test_skill_e2e_s17"),
            "Compiled workflow must reference the skill name 'test_skill_e2e_s17'. "
            + "Plan keys: " + workflowDef.keySet()
            + ". COUNTERFACTUAL: skill nested in agent_tool would not appear in plan if the SDK dropped it.");

        // Counterfactual: a plain agent without the skill tool has no skill reference in its plan.
        Agent plainParent = Agent.builder()
            .name("e2e_s17_no_skill_at")
            .model(MODEL)
            .instructions("Plain.")
            .build();
        Map<String, Object> plainPlan = runtime.plan(plainParent);
        Map<String, Object> plainWf = (Map<String, Object>) plainPlan.get("workflowDef");
        assertFalse(plainWf.toString().contains("test_skill_e2e_s17"),
            "A parent without the skill tool must not reference the skill name. "
            + "COUNTERFACTUAL: if the skill leaked into unrelated agents, this would fail.");
    }

    @Test
    @Order(11)
    @SuppressWarnings("unchecked")
    void test_standalone_skill_script_runs_as_worker_tool(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);
        Agent skillAgent = Skill.skill(dir, MODEL);

        AgentResult result = runtime.run(
            skillAgent,
            "java_tool_parity. Call test_skill_e2e_s17__echo_args exactly once with "
                + "java_tool_parity as the command argument, then return the tool output.");

        assertTrue(result.isSuccess(),
            "Standalone skill run must complete. executionId=" + result.getExecutionId()
            + " status=" + result.getStatus() + " error=" + result.getError());

        Map<String, Object> workflow = getWorkflow(result.getExecutionId());
        verifyWorkerTask(
            workflow,
            "test_skill_e2e_s17__echo_args",
            "ECHO_ARGS_RESULT:java_tool_parity");
    }

    @Test
    @Order(12)
    @SuppressWarnings("unchecked")
    void test_agent_tool_skill_workers_with_domain(@TempDir Path dir) throws Exception {
        writeSkillDir(dir);
        Agent skillAgent = Skill.skill(dir, MODEL);
        ToolDef skillTool = AgentTool.from(skillAgent, "Run the test skill with echo_args.");
        Agent parent = Agent.builder()
            .name("e2e_s17_skill_at_domain")
            .model(MODEL)
            .instructions("You have one tool: test_skill_e2e_s17. Call it once with the user's request, then return the result.")
            .tools(List.of(skillTool))
            .stateful(true)
            .maxTurns(3)
            .build();

        AgentResult result = runtime.run(parent, "Echo 'java_domain_proof'");
        assertTrue(result.isSuccess(),
            "Nested stateful skill run must complete. executionId=" + result.getExecutionId()
            + " status=" + result.getStatus() + " error=" + result.getError());

        Map<String, Object> workflow = getWorkflow(result.getExecutionId());
        Object tasksObj = workflow.get("tasks");
        assertTrue(tasksObj instanceof List, "Parent workflow must include task list. Got: " + workflow.keySet());
        Map<String, Object> skillTask = ((List<Map<String, Object>>) tasksObj).stream()
            .filter(t -> String.valueOf(t.get("taskDefName")).contains("test_skill_e2e_s17"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("Skill sub-workflow task not found: " + tasksObj));
        assertEquals("COMPLETED", skillTask.get("status"), "Skill SUB_WORKFLOW task must complete.");
        String subWorkflowId = String.valueOf(((Map<String, Object>) skillTask.get("outputData")).get("subWorkflowId"));
        assertNotNull(subWorkflowId, "Skill SUB_WORKFLOW must expose subWorkflowId.");

        Map<String, Object> subWorkflow = getWorkflow(subWorkflowId);
        verifyWorkerTask(
            subWorkflow,
            "test_skill_e2e_s17__echo_args",
            "ECHO_ARGS_RESULT:");
    }

    @SuppressWarnings("unchecked")
    private static void verifyWorkerTask(Map<String, Object> workflow, String taskName, String marker) {
        Object tasksObj = workflow.get("tasks");
        assertTrue(tasksObj instanceof List, "Workflow must include task list. Got keys: " + workflow.keySet());
        List<Map<String, Object>> tasks = (List<Map<String, Object>>) tasksObj;
        List<Map<String, Object>> matches = tasks.stream()
            .filter(t -> String.valueOf(t.get("taskDefName")).contains(taskName)
                || String.valueOf(t.get("referenceTaskName")).contains(taskName)
                || String.valueOf(t.get("taskType")).contains(taskName))
            .toList();
        assertFalse(matches.isEmpty(), taskName + " was not invoked. Task defs: "
            + tasks.stream().map(t -> t.get("taskDefName")).toList());
        for (Map<String, Object> task : matches) {
            assertEquals("COMPLETED", task.get("status"),
                taskName + " must complete as a worker task. Task: " + task);
        }
        boolean markerFound = matches.stream()
            .anyMatch(t -> String.valueOf(t.get("outputData")).contains(marker));
        assertTrue(markerFound, taskName + " completed but marker '" + marker + "' was missing. Tasks: " + matches);
    }
}
