/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.util;

import static org.assertj.core.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.*;

class PlanCompilerScriptTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private Context graalCtx;

    @BeforeEach
    void setUp() {
        graalCtx = Context.newBuilder("js").allowAllAccess(true).build();
    }

    @AfterEach
    void tearDown() {
        graalCtx.close();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> compilePlan(String planJson) throws Exception {
        String script = JavaScriptBuilder.compilePlanToWorkflowScript();
        String wrappedScript = "var $ = {"
                + "planJson: " + MAPPER.writeValueAsString(planJson) + ","
                + "parentName: 'test_harness',"
                + "model: 'openai/gpt-4o-mini'"
                + "}; var __result = " + script + ";";
        graalCtx.eval("js", wrappedScript);
        Value resultVal = graalCtx.eval("js", "__result");
        // Surface compile errors so tests fail with the actual reason instead of NPE.
        if (resultVal.hasMember("error") && !resultVal.getMember("error").isNull()) {
            throw new AssertionError("Plan compilation failed: " + resultVal.getMember("error").asString());
        }
        String resultJson = resultVal.getMember("workflow_def").asString();
        assertThat(resultJson).as("workflow_def should be non-null").isNotNull();
        return (Map<String, Object>) MAPPER.readValue(resultJson, Map.class);
    }

    /**
     * Compile expecting failure: returns the {@code error} string the compiler
     * produced. Throws if the compile unexpectedly succeeded.
     */
    private String compilePlanExpectError(String planJson) throws Exception {
        String script = JavaScriptBuilder.compilePlanToWorkflowScript();
        String wrappedScript = "var $ = {"
                + "planJson: " + MAPPER.writeValueAsString(planJson) + ","
                + "parentName: 'test_harness',"
                + "model: 'openai/gpt-4o-mini'"
                + "}; var __result = " + script + ";";
        graalCtx.eval("js", wrappedScript);
        Value resultVal = graalCtx.eval("js", "__result");
        if (!resultVal.hasMember("error") || resultVal.getMember("error").isNull()) {
            String wfDef = resultVal.getMember("workflow_def").asString();
            throw new AssertionError(
                    "Expected compile error but got workflow_def: " + wfDef.substring(0, Math.min(200, wfDef.length())));
        }
        return resultVal.getMember("error").asString();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> allTasks(Map<String, Object> wf) {
        List<Map<String, Object>> all = new ArrayList<>();
        collectTasks((List<Map<String, Object>>) wf.get("tasks"), all);
        return all;
    }

    @SuppressWarnings("unchecked")
    private void collectTasks(List<Map<String, Object>> tasks, List<Map<String, Object>> out) {
        if (tasks == null) return;
        for (var t : tasks) {
            out.add(t);
            if ("FORK_JOIN".equals(t.get("type"))) {
                var forkTasks = (List<List<Map<String, Object>>>) t.get("forkTasks");
                if (forkTasks != null) forkTasks.forEach(branch -> collectTasks(branch, out));
            }
        }
    }

    @Test
    void testSuccessConditionProducesEvalInlineTask() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "run_cmd", "args": {"command": "echo hello"}}
                  ]}],
                  "validation": [{"tool": "run_tests", "success_condition": "$.exit_code === 0"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);

        boolean hasEvalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .anyMatch(t -> {
                    @SuppressWarnings("unchecked")
                    var inputs = (Map<String, Object>) t.get("inputParameters");
                    if (inputs == null) return false;
                    String expr = String.valueOf(inputs.getOrDefault("expression", ""));
                    return expr.contains("exit_code") && expr.contains("passed");
                });
        assertThat(hasEvalTask)
                .as("Expected an INLINE task evaluating success_condition '$.exit_code === 0'")
                .isTrue();

        // Verify the INLINE eval task's toolOut input parameter references the SIMPLE validation task's output
        Map<String, Object> valSimpleTask = tasks.stream()
                .filter(t -> "SIMPLE".equals(t.get("type")) && "run_tests".equals(t.get("name")))
                .findFirst()
                .orElseThrow(() -> new AssertionError("No SIMPLE validation task found for run_tests"));

        String simpleRef = (String) valSimpleTask.get("taskReferenceName");

        Map<String, Object> evalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .filter(t -> {
                    @SuppressWarnings("unchecked")
                    var inp = (Map<String, Object>) t.get("inputParameters");
                    if (inp == null) return false;
                    String expr = String.valueOf(inp.getOrDefault("expression", ""));
                    return expr.contains("exit_code") && expr.contains("passed");
                })
                .findFirst()
                .orElseThrow(() -> new AssertionError("No INLINE eval task with success_condition found"));

        @SuppressWarnings("unchecked")
        Map<String, Object> evalInputs = (Map<String, Object>) evalTask.get("inputParameters");
        String toolOutRef = (String) evalInputs.get("toolOut");
        assertThat(toolOutRef)
                .as("INLINE eval task's toolOut must reference the SIMPLE validation task output")
                .contains(simpleRef)
                .contains(".output.result");
    }

    @Test
    void testNoSuccessConditionUsesDefaultPassCheck() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [{"tool": "check_file"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);

        boolean hasDefaultEvalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .anyMatch(t -> {
                    @SuppressWarnings("unchecked")
                    var inputs = (Map<String, Object>) t.get("inputParameters");
                    if (inputs == null) return false;
                    String expr = String.valueOf(inputs.getOrDefault("expression", ""));
                    return expr.contains("passed");
                });
        assertThat(hasDefaultEvalTask)
                .as("Expected an INLINE eval task wrapping the validation SIMPLE task even without success_condition")
                .isTrue();
    }

    @Test
    void testMultipleValidationsUseForkJoin() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [
                    {"tool": "lint", "success_condition": "$.passed === true"},
                    {"tool": "run_tests", "success_condition": "$.exit_code === 0"}
                  ]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> topTasks = (List<Map<String, Object>>) wf.get("tasks");

        boolean hasForkJoin = topTasks.stream().anyMatch(t -> "FORK_JOIN".equals(t.get("type")));
        assertThat(hasForkJoin).as("Multiple validations should compile to a FORK_JOIN").isTrue();

        @SuppressWarnings("unchecked")
        Map<String, Object> forkTask = topTasks.stream()
                .filter(t -> "FORK_JOIN".equals(t.get("type")))
                .findFirst().orElseThrow();
        @SuppressWarnings("unchecked")
        var forkTasks = (List<List<Map<String, Object>>>) forkTask.get("forkTasks");
        assertThat(forkTasks).hasSize(2);

        // Each branch must be [SIMPLE, INLINE] — the tool task + eval task
        assertThat(forkTasks.get(0)).hasSize(2);
        assertThat(forkTasks.get(1)).hasSize(2);

        // First task in each branch should be SIMPLE (tool call)
        Map<String, Object> branch0task0 = forkTasks.get(0).get(0);
        Map<String, Object> branch0task1 = forkTasks.get(0).get(1);
        assertThat(branch0task0.get("type")).isEqualTo("SIMPLE");
        assertThat(branch0task1.get("type")).isEqualTo("INLINE");

        Map<String, Object> branch1task0 = forkTasks.get(1).get(0);
        Map<String, Object> branch1task1 = forkTasks.get(1).get(1);
        assertThat(branch1task0.get("type")).isEqualTo("SIMPLE");
        assertThat(branch1task1.get("type")).isEqualTo("INLINE");
    }

    @Test
    void testSingleValidationDoesNotUseForkJoin() throws Exception {
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [{"tool": "run_tests", "success_condition": "$.exit_code === 0"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> topTasks = (List<Map<String, Object>>) wf.get("tasks");

        boolean hasForkJoin = topTasks.stream().anyMatch(t -> "FORK_JOIN".equals(t.get("type")));
        assertThat(hasForkJoin).as("Single validation should NOT use FORK_JOIN").isFalse();
    }

    // ── Failure-mode tests (validate the new fail-closed paths) ──────

    @Test
    void testCycleInDependsOnIsRejected() throws Exception {
        // a → b → a — old behavior was silent partial-DAG; new behavior must
        // surface a structured error with the full cycle path.
        String planJson = """
                {
                  "steps": [
                    {"id": "a", "depends_on": ["b"], "operations": [{"tool": "noop", "args": {}}]},
                    {"id": "b", "depends_on": ["a"], "operations": [{"tool": "noop", "args": {}}]}
                  ]
                }""";
        String error = compilePlanExpectError(planJson);
        assertThat(error).as("cycle error must include the cycle path").contains("Cycle in depends_on");
        assertThat(error).contains("->");
    }

    @Test
    void testDuplicateStepIdIsRejected() throws Exception {
        String planJson = """
                {
                  "steps": [
                    {"id": "s1", "operations": [{"tool": "noop", "args": {}}]},
                    {"id": "s1", "operations": [{"tool": "noop", "args": {}}]}
                  ]
                }""";
        String error = compilePlanExpectError(planJson);
        assertThat(error).contains("Duplicate step id: s1");
    }

    @Test
    void testEmptyStepsArrayIsRejected() throws Exception {
        String error = compilePlanExpectError("{\"steps\": []}");
        assertThat(error).contains("non-empty steps array");
    }

    @Test
    void testUnsafeSuccessConditionIsRejected() throws Exception {
        // Planner-supplied success_condition that would attempt a hang, host
        // access, or sandbox escape. safeCondition must reject all of these.
        String[] unsafeConditions = {
            // Original cases — keywords/loops/host access
            "function() { while (true) {} }",
            "$.x === 1; while(1){}",
            "Java.type('java.lang.Runtime')",
            "eval('1+1')",
            "$.x = 5",
            "var foo = 1",
            // Round-2 finds — sandbox-escape primitives
            "$.constructor.constructor('return Java.type(0)')()",
            "$.constructor",
            "$.prototype.foo",
            "$.__proto__",
            // Bracket access (not allowed at all — would also bypass identifier check)
            "$['constructor']",
            "$.x['__proto__']",
            // Comma operator (sequence with side effect)
            "$.x === 1, eval('1')",
            // String concatenation to spell forbidden identifiers
            "$['c'+'onstructor']",
            // Backslash (escape evasion / unicode escapes)
            "$.\\u0063onstructor",
            // Backtick (template literals)
            "`${$.x}` === '1'",
            // Ternary (control flow)
            "$.x ? 1 : 0",
            // Object/Reflect/Proxy globals
            "Object.keys($).length > 0",
            "Reflect.get($, 'x')",
            "Proxy",
            // Defensive: __defineGetter__ (older sandbox escape vector)
            "$.__defineGetter__",
            // Bare assignment in deeper position
            "(function(){ x = 1; return $.y; })()",
        };
        for (String unsafe : unsafeConditions) {
            String planJson = String.format(
                    """
                            {
                              "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}],
                              "validation": [{"tool": "check", "success_condition": %s}]
                            }""",
                    MAPPER.writeValueAsString(unsafe));
            String error = compilePlanExpectError(planJson);
            assertThat(error)
                    .as("unsafe success_condition '%s' must be rejected", unsafe)
                    .contains("unsafe success_condition");
        }
    }

    @Test
    void testSuccessConditionAllowsLiteralBannedWordInString() throws Exception {
        // Counter-test: a banned identifier appearing inside a string LITERAL
        // (not as an identifier reference) is legitimate and must be accepted.
        // safeCondition strips strings before identifier-checking so this works.
        String[] safeWithLiterals = {
            "$.kind === 'constructor'",
            "$.role !== 'eval-pending'",
            "$.msg === 'Function returned ok'",
        };
        for (String cond : safeWithLiterals) {
            String planJson = String.format(
                    """
                            {
                              "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}],
                              "validation": [{"tool": "check", "success_condition": %s}]
                            }""",
                    MAPPER.writeValueAsString(cond));
            // Must compile cleanly.
            Map<String, Object> wf = compilePlan(planJson);
            assertThat(wf)
                    .as("safe condition '%s' (banned word in string literal) should compile",
                            cond)
                    .isNotNull();
        }
    }

    @Test
    void testSafeSuccessConditionsAreAccepted() throws Exception {
        // Counter-test: representative safe conditions must compile.
        String[] safeConditions = {
            "$.exit_code === 0",
            "$.passed === true",
            "$.indexOf('passed') >= 0",
            "$.count > 0 && $.errors === 0",
            "$.status !== 'ERROR'",
        };
        for (String safe : safeConditions) {
            String planJson = String.format(
                    """
                            {
                              "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}],
                              "validation": [{"tool": "check", "success_condition": %s}]
                            }""",
                    MAPPER.writeValueAsString(safe));
            // Must compile cleanly; compilePlan throws if there's an error.
            Map<String, Object> wf = compilePlan(planJson);
            assertThat(wf).as("safe condition '%s' should compile", safe).isNotNull();
        }
    }

    @Test
    void testJsonSchemaAsOutputSchemaIsRejected() throws Exception {
        // Real JSON Schema (with type+properties) was previously parsed as if
        // its top-level keys were tool args, producing toolInputs.type and
        // toolInputs.properties garbage. Must now be rejected.
        String jsonSchemaShape = "{\\\"type\\\":\\\"object\\\",\\\"properties\\\":{\\\"x\\\":{\\\"type\\\":\\\"string\\\"}}}";
        String planJson = "{"
                + "\"steps\": [{\"id\": \"s1\", \"operations\": [{"
                + "\"tool\": \"do_thing\","
                + "\"generate\": {"
                + "\"instructions\": \"do it\","
                + "\"output_schema\": \""
                + jsonSchemaShape
                + "\""
                + "}}]}]}";
        String error = compilePlanExpectError(planJson);
        assertThat(error).contains("JSON Schema").contains("example object instead");
    }

    @Test
    void testInstanceShapeOutputSchemaIsAccepted() throws Exception {
        // Counter-test: a plain instance-shape example (no type+properties) must compile.
        String planJson = "{"
                + "\"steps\": [{\"id\": \"s1\", \"operations\": [{"
                + "\"tool\": \"write_file\","
                + "\"generate\": {"
                + "\"instructions\": \"write hello\","
                + "\"output_schema\": \"{\\\"path\\\":\\\"...\\\",\\\"content\\\":\\\"...\\\"}\""
                + "}}]}]}";
        Map<String, Object> wf = compilePlan(planJson);
        assertThat(wf).isNotNull();
    }

    @Test
    void testGeneratedOpUsesParseGateSwitch() throws Exception {
        // Verify the parse-error short-circuit: every generated op chain must
        // include a SWITCH after the parse INLINE so the tool task can't fire
        // with all-undefined args when the LLM JSON is malformed.
        String planJson = """
                {
                  "steps": [{"id": "s1", "operations": [{
                    "tool": "write_file",
                    "generate": {
                      "instructions": "write",
                      "output_schema": "{\\"path\\":\\"...\\"}"
                    }
                  }]}]
                }""";
        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);
        boolean hasParseGate = tasks.stream()
                .anyMatch(t -> "SWITCH".equals(t.get("type"))
                        && String.valueOf(t.get("taskReferenceName")).startsWith("pgate_"));
        assertThat(hasParseGate)
                .as("Generated op must produce a parse-gate SWITCH")
                .isTrue();
    }

    @Test
    void testNoTaskIsOptional() throws Exception {
        // Verify the optional:true cancer is gone: every emitted task in a
        // typical plan must have optional unset (defaults to false). Failures
        // bubble through SUB_WORKFLOW so the parent SWITCH can route to fallback.
        String planJson = """
                {
                  "steps": [
                    {"id": "s1", "operations": [
                      {"tool": "static_op", "args": {"x": 1}},
                      {"tool": "gen_op", "generate": {"instructions": "go", "output_schema": "{\\"y\\":\\"...\\"}"}}
                    ]}
                  ],
                  "validation": [{"tool": "check", "success_condition": "$.passed === true"}],
                  "on_success": [{"tool": "celebrate", "args": {}}],
                  "on_failure": [{"tool": "log_failure", "args": {}}]
                }""";
        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);
        long optionalCount = tasks.stream()
                .filter(t -> Boolean.TRUE.equals(t.get("optional")))
                .count();
        assertThat(optionalCount)
                .as("No task in the compiled plan should be optional:true")
                .isZero();
    }

    @Test
    void testValidationSwitchFailsClosed() throws Exception {
        // The validation SWITCH must route 'passed' → onSuccess and *anything
        // else* (failed, null, garbage) → onFailure as defaultCase.
        String planJson = """
                {
                  "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}],
                  "validation": [{"tool": "check", "success_condition": "$.passed === true"}],
                  "on_success": [{"tool": "celebrate", "args": {}}],
                  "on_failure": [{"tool": "log_failure", "args": {}}]
                }""";
        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);
        @SuppressWarnings("unchecked")
        Map<String, Object> validationSwitch = tasks.stream()
                .filter(t -> "SWITCH".equals(t.get("type"))
                        && String.valueOf(t.get("taskReferenceName")).startsWith("vsw_"))
                .findFirst()
                .orElseThrow(() -> new AssertionError("validation SWITCH not found"));
        @SuppressWarnings("unchecked")
        Map<String, Object> decisionCases = (Map<String, Object>) validationSwitch.get("decisionCases");
        assertThat(decisionCases.keySet()).contains("passed");
        // defaultCase must be onFailure (TERMINATE among others), not onSuccess.
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> defaultCase = (List<Map<String, Object>>) validationSwitch.get("defaultCase");
        boolean defaultHasTerminate =
                defaultCase.stream().anyMatch(t -> "TERMINATE".equals(t.get("type")));
        assertThat(defaultHasTerminate)
                .as("defaultCase must include TERMINATE — fail-closed semantics")
                .isTrue();
    }

    @Test
    void testTimeoutFromHarnessConfig() throws Exception {
        // harnessTimeoutSeconds input flows through to the compiled WorkflowDef.
        String planJson = """
                {
                  "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}]
                }""";
        String script = JavaScriptBuilder.compilePlanToWorkflowScript();
        String wrappedScript = "var $ = {"
                + "planJson: " + MAPPER.writeValueAsString(planJson) + ","
                + "parentName: 'test_harness',"
                + "model: 'openai/gpt-4o-mini',"
                + "harnessTimeoutSeconds: 1234"
                + "}; var __result = " + script + ";";
        graalCtx.eval("js", wrappedScript);
        Value resultVal = graalCtx.eval("js", "__result");
        @SuppressWarnings("unchecked")
        Map<String, Object> wf =
                (Map<String, Object>) MAPPER.readValue(resultVal.getMember("workflow_def").asString(), Map.class);
        assertThat(wf.get("timeoutSeconds"))
                .as("timeoutSeconds should track harnessTimeoutSeconds input")
                .isEqualTo(1234);
    }

    @Test
    void testDefaultTimeoutWhenHarnessTimeoutAbsent() throws Exception {
        // No harness timeout → fall back to 600.
        Map<String, Object> wf = compilePlan(
                """
                        {
                          "steps": [{"id": "s1", "operations": [{"tool": "noop", "args": {}}]}]
                        }""");
        assertThat(wf.get("timeoutSeconds")).isEqualTo(600);
    }

    @Test
    void testWorkflowDefIsNotArrayWrapped() throws Exception {
        // Old behavior: JSON.stringify([wfDef]) and parse_wf unwrap arr[0].
        // New behavior: bare object — verify by direct JSON parse.
        String script = JavaScriptBuilder.compilePlanToWorkflowScript();
        String wrappedScript = "var $ = {"
                + "planJson: '{\"steps\": [{\"id\": \"s1\", \"operations\": [{\"tool\": \"noop\", \"args\": {}}]}]}',"
                + "parentName: 'test_harness',"
                + "model: 'openai/gpt-4o-mini'"
                + "}; var __result = " + script + ";";
        graalCtx.eval("js", wrappedScript);
        Value resultVal = graalCtx.eval("js", "__result");
        String wfDefStr = resultVal.getMember("workflow_def").asString();
        // Must parse as a single object, not an array.
        Object parsed = MAPPER.readValue(wfDefStr, Object.class);
        assertThat(parsed).isInstanceOf(Map.class);
    }

    @Test
    void testSuccessConditionWorksWithPlainTextOutput() throws Exception {
        // success_condition receives plain-text tool output (not JSON) — e.g., pytest output
        // The condition uses $.indexOf(...) — requires $ to be the raw string, not {}
        String planJson = """
                {
                  "steps": [{"id": "s1", "parallel": false, "operations": [
                    {"tool": "noop", "args": {}}
                  ]}],
                  "validation": [{"tool": "run_tests", "success_condition": "$.indexOf('passed') >= 0"}]
                }""";

        Map<String, Object> wf = compilePlan(planJson);
        List<Map<String, Object>> tasks = allTasks(wf);

        // Find the INLINE eval task
        @SuppressWarnings("unchecked")
        Map<String, Object> evalTask = tasks.stream()
                .filter(t -> "INLINE".equals(t.get("type")))
                .filter(t -> {
                    var inp = (Map<String, Object>) t.get("inputParameters");
                    if (inp == null) return false;
                    return String.valueOf(inp.getOrDefault("expression", "")).contains("indexOf");
                })
                .findFirst()
                .orElseThrow(() -> new AssertionError("No INLINE eval task with indexOf condition found"));

        @SuppressWarnings("unchecked")
        Map<String, Object> evalInputs = (Map<String, Object>) evalTask.get("inputParameters");
        String evalExpr = (String) evalInputs.get("expression");

        // Simulate executing the eval expression with plain-text tool output "1 passed in 0.3s"
        // The expression references $.toolOut — we inject it directly
        String testScript = "var $ = {toolOut: '1 passed in 0.3s'}; var __evalResult = " + evalExpr + ";";
        graalCtx.eval("js", testScript);
        Value result = graalCtx.eval("js", "__evalResult");

        // Must return {passed: true} — not {passed: false} due to JSON.parse failure
        assertThat(result.getMember("passed").asBoolean())
                .as("success_condition with $.indexOf on plain-text output must return passed=true")
                .isTrue();
    }
}
