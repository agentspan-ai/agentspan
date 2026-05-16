// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.


import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.internal.AgentConfigSerializer;
import ai.agentspan.skill.Skill;
import ai.agentspan.skill.SkillLoadError;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
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
            + "1. Call echo_args with the user input.\n"
            + "2. Return the result.\n";
        Files.writeString(dir.resolve("SKILL.md"), skillMd);
        Files.writeString(dir.resolve("alpha-agent.md"), "# Alpha Agent\nYou analyze the input.\n");
        Files.writeString(dir.resolve("beta-agent.md"), "# Beta Agent\nYou summarize the analysis.\n");

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
}
