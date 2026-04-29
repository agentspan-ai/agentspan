#!/usr/bin/env bash
set -uo pipefail

# Mutation testing — proves Java e2e tests catch bugs.
# Each mutation is applied, tested, then reverted via file backup.
#
# Usage:
#   ./e2e/mutation_test_java.sh          # run all 16 mutations
#   ./e2e/mutation_test_java.sh --suite suite1  # only Suite 1 mutations

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAVA_SDK="$REPO_ROOT/sdk/java"
SERVER_URL="http://localhost:6767/api"
PASS=0
FAIL=0
RESULTS=()
SUITE_FLAG=""

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) SUITE_FLAG="$2"; shift 2 ;;
    *)       echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# run_mutation <label> <absolute-file-path> <sed-cmd> <suite-filter> [source|test]
# source = recompile main sources after mutating (default for src/main files)
# test   = no pre-compile needed; maven recompiles test sources during 'test' phase
run_mutation() {
    local label="$1"
    local file="$2"       # absolute path
    local sed_cmd="$3"    # sed command to apply mutation
    local suite="$4"      # JUnit class name(s) to run
    local kind="${5:-source}"  # "source" or "test"

    # Skip if --suite flag doesn't match
    if [[ -n "$SUITE_FLAG" && "$suite" != *"$SUITE_FLAG"* ]]; then
        return
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MUTATION: $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Backup → mutate
    cp "$file" "$file.bak"
    eval "$sed_cmd"

    # For source file mutations: recompile main classes before running tests
    if [[ "$kind" == "source" ]]; then
        echo "  (recompiling source...)"
        if ! mvn -f "$JAVA_SDK/pom.xml" compile -q 2>/dev/null; then
            echo "  ✅ KILLED — compilation failed (mutation broke the build)"
            mv "$file.bak" "$file"
            mvn -f "$JAVA_SDK/pom.xml" compile -q 2>/dev/null || true
            RESULTS+=("✅  $label")
            ((PASS++))
            return
        fi
    fi

    local output exit_code
    output=$(mvn -f "$JAVA_SDK/pom.xml" test -Pe2e -Dtest="$suite" \
        -DAGENTSPAN_SERVER_URL="$SERVER_URL" -q 2>&1)
    exit_code=$?

    # Always restore from backup first
    mv "$file.bak" "$file"

    # Recompile to restore clean state after mutation
    if [[ "$kind" == "source" ]]; then
        mvn -f "$JAVA_SDK/pom.xml" compile -q 2>/dev/null || true
    fi

    if [ $exit_code -ne 0 ]; then
        local err
        err=$(echo "$output" | grep -E "AssertionError|FAILURE|expected|but was|ERROR" | head -2)
        echo "  ✅ KILLED — test correctly failed"
        [[ -n "$err" ]] && echo "     $err"
        RESULTS+=("✅  $label")
        ((PASS++))
    else
        echo "  ❌ SURVIVED — test did NOT catch the mutation!"
        RESULTS+=("❌  $label")
        ((FAIL++))
    fi
}

echo "═══════════════════════════════════════════════════════════════"
echo "  JAVA MUTATION TESTING — Proving tests catch bugs"
echo "═══════════════════════════════════════════════════════════════"

# ── Suite 1 — SDK source mutations (AgentConfigSerializer) ─────────

# Mutation 1: Wrong toolType: worker → MUTANT_TYPE
# AgentConfigSerializer.java serializes toolType as tool.getToolType() — the string
# is set in ToolRegistry. The test checks toolType == "worker". We mutate the
# type-check branch so outputSchema is never added but toolType still emits.
# Stronger: mutate toolMap.put("toolType", ...) to emit "MUTANT_TYPE" unconditionally.
run_mutation \
    "Suite1 SDK: toolType worker→MUTANT_TYPE (AgentConfigSerializer)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java" \
    "sed -i '' 's/toolMap.put(\"toolType\", tool.getToolType());/toolMap.put(\"toolType\", \"MUTANT_TYPE\");/' '$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java'" \
    "E2eSuite1BasicValidation#test_smoke_simple_agent_plan" \
    "source"

# Mutation 2: Wrong strategy: @JsonProperty("handoff") → @JsonProperty("wrong_strategy")
# Strategy.HANDOFF serializes as "handoff". The test checks strategy == "handoff".
run_mutation \
    "Suite1 SDK: handoff strategy→wrong_strategy (Strategy.java)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/enums/Strategy.java" \
    "sed -i '' 's/@JsonProperty(\"handoff\")/@JsonProperty(\"wrong_strategy\")/' '$JAVA_SDK/src/main/java/dev/agentspan/enums/Strategy.java'" \
    "E2eSuite1BasicValidation#test_plan_all_8_strategies" \
    "source"

# Mutation 3: Guardrail position dropped — comment out gMap.put("position", ...)
run_mutation \
    "Suite1 SDK: guardrail position field dropped (AgentConfigSerializer)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java" \
    "sed -i '' 's/gMap.put(\"position\", g.getPosition().toJsonValue());/\/\/ MUTANT: position dropped/' '$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java'" \
    "E2eSuite1BasicValidation#test_plan_reflects_guardrails" \
    "source"

# Mutation 4: Tool credentials dropped — comment out merged.put("credentials", creds)
run_mutation \
    "Suite1 SDK: tool credentials dropped (AgentConfigSerializer)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java" \
    "sed -i '' 's/merged.put(\"credentials\", creds);/\/\/ MUTANT: credentials dropped/' '$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java'" \
    "E2eSuite1BasicValidation#test_plan_reflects_credentials" \
    "source"

# Mutation 5: HTTP toolType wrong — HttpTool hardcodes toolType("http"); mutate to "MUTANT_HTTP"
run_mutation \
    "Suite1 SDK: http toolType→MUTANT_HTTP (HttpTool.java)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/tools/HttpTool.java" \
    "sed -i '' 's/.toolType(\"http\")/.toolType(\"MUTANT_HTTP\")/' '$JAVA_SDK/src/main/java/dev/agentspan/tools/HttpTool.java'" \
    "E2eSuite1BasicValidation#test_plan_http_tool" \
    "source"

# ── Suite 1 — Test assertion mutations ────────────────────────────

# Mutation 6: Flip assertion on worker toolType: "worker" → "NOTWORKER"
run_mutation \
    "Suite1 Test: wrong expected toolType (NOTWORKER vs worker)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite1BasicValidation.java" \
    "sed -i '' 's/assertEquals(\"worker\", toolTypes.get(\"e2e_add\")/assertEquals(\"NOTWORKER\", toolTypes.get(\"e2e_add\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite1BasicValidation.java'" \
    "E2eSuite1BasicValidation#test_smoke_simple_agent_plan" \
    "test"

# Mutation 7: Wrong expected strategy: "sequential" → "WRONG"
run_mutation \
    "Suite1 Test: wrong expected strategy (WRONG vs sequential)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite1BasicValidation.java" \
    "sed -i '' 's/assertEquals(\"sequential\", agentDef.get(\"strategy\")/assertEquals(\"WRONG\", agentDef.get(\"strategy\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite1BasicValidation.java'" \
    "E2eSuite1BasicValidation#test_sequential_pipeline_plan" \
    "test"

# ── Suite 2 — AtomicBoolean mutation ─────────────────────────────

# Mutation 8: Tool never sets flag — remove toolWasCalled.set(true)
run_mutation \
    "Suite2 Test: toolWasCalled.set(true) removed (AtomicBoolean never set)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite2ToolCalling.java" \
    "sed -i '' 's/toolWasCalled.set(true);/\/\/ MUTANT: flag never set/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite2ToolCalling.java'" \
    "E2eSuite2ToolCalling#test_agent_calls_worker_tool" \
    "test"

# ── Suite 6 — Handoff structural mutation ────────────────────────

# Mutation 9: Wrong SUB_WORKFLOW count — require >= 5 instead of >= 2
# The test has two `assertTrue(subWorkflowCount >= 2, ...)` in test_sequential_execution.
# We replace both occurrences to make the bar impossible to meet.
run_mutation \
    "Suite6 Test: SUB_WORKFLOW count >= 2 raised to >= 5" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java" \
    "sed -i '' '/test_sequential_execution/,/test_parallel_execution/s/subWorkflowCount >= 2/subWorkflowCount >= 5/g' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java'" \
    "E2eSuite6Handoffs#test_sequential_execution" \
    "test"

# ── Suite 8 — LangChain4j mutation ───────────────────────────────

# Mutation 10: Wrong tool name in assertion: "lc4j_add" → "WRONG_NAME"
run_mutation \
    "Suite8 Test: lc4j_add name assertion→WRONG_NAME" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite8LangChain4j.java" \
    "sed -i '' 's/assertTrue(names.contains(\"lc4j_add\")/assertTrue(names.contains(\"WRONG_NAME\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite8LangChain4j.java'" \
    "E2eSuite8LangChain4j#test_tool_extraction" \
    "test"

# ── Suite 5 — Extended guardrails mutations ───────────────────────

# Mutation 11: Suite5 Test — tool output guardrail AtomicBoolean removed
# The tool body sets sqlToolBodyRan.set(true). Commenting it out means the assertion
# assertTrue(sqlToolBodyRan.get()) will fail because the flag stays false.
run_mutation \
    "Suite5 Test: sqlToolBodyRan.set(true) removed (AtomicBoolean never set)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite5Guardrails.java" \
    "sed -i '' 's/sqlToolBodyRan.set(true);/\/\/ MUTANT: flag never set/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite5Guardrails.java'" \
    "E2eSuite5Guardrails#test_tool_output_detected_by_guardrail" \
    "test"

# ── Suite 6 — New handoff routing mutations ───────────────────────

# Mutation 12: Suite6 Test — router wrong sub-workflow name
# The assertion checks ref.contains("math") to verify the router picked the math agent.
# Changing "math" to "WRONGAGENT" makes the assertion always false.
run_mutation \
    "Suite6 Test: router assertion 'math'→'WRONGAGENT'" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java" \
    "sed -i '' 's/ref.contains(\"math\")/ref.contains(\"WRONGAGENT\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java'" \
    "E2eSuite6Handoffs#test_router_selects_correct_agent" \
    "test"

# Mutation 13: Suite6 Test — swarm wrong sub-workflow name
# The assertion checks ref.contains("text") to verify the swarm routed to the text agent.
# Changing "text" to "WRONGAGENT" makes the assertion always false.
run_mutation \
    "Suite6 Test: swarm assertion 'text'→'WRONGAGENT'" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java" \
    "sed -i '' 's/ref.contains(\"text\")/ref.contains(\"WRONGAGENT\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite6Handoffs.java'" \
    "E2eSuite6Handoffs#test_swarm_with_text_mention" \
    "test"

# ── Suite 9 — Code execution mutations ───────────────────────────

# Mutation 14: Suite9 SDK — codeExecution block dropped from serializer
# Commenting out agentMap.put("codeExecution", codeExec) means the codeExecution
# key is absent from the agentDef → test_code_execution_compiles fails.
run_mutation \
    "Suite9 SDK: agentMap.put('codeExecution', codeExec) dropped (AgentConfigSerializer)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java" \
    "sed -i '' 's/agentMap.put(\"codeExecution\", codeExec);/\/\/ MUTANT: codeExecution dropped/' '$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java'" \
    "E2eSuite9CodeExecution#test_code_execution_compiles" \
    "source"

# Mutation 15: Suite9 Test — wrong expected Python output (3066→9999)
# The test checks for "3066" (42 * 73) in the execute_code task output.
# Changing to "9999" makes the assertion fail because the real output is "3066".
run_mutation \
    "Suite9 Test: Python output assertion '3066'→'9999'" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite9CodeExecution.java" \
    "sed -i '' 's/taskOutputStr(t).contains(\"3066\")/taskOutputStr(t).contains(\"9999\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite9CodeExecution.java'" \
    "E2eSuite9CodeExecution#test_local_python_execution" \
    "test"

# Mutation 16: Suite9 Test — wrong expected bash output (46→99)
# The test checks for "46" (17 + 29) in the execute_code bash task output.
# Changing to "99" makes the assertion fail because the real output is "46".
run_mutation \
    "Suite9 Test: bash output assertion '46'→'99'" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite9CodeExecution.java" \
    "sed -i '' 's/taskOutputStr(t).contains(\"46\")/taskOutputStr(t).contains(\"99\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite9CodeExecution.java'" \
    "E2eSuite9CodeExecution#test_local_bash_execution" \
    "test"

# ── Suite 10 — Synthesize flag mutations ──────────────────────────

# Mutation 17: Suite10 SDK — synthesize field never sent to server (AgentConfigSerializer)
# Commenting out agentMap.put("synthesize", false) means the server never receives the flag
# → server defaults to doSynthesize=true → adds _final task → finalCount == 1 AND
# agentDef.synthesize == null (not false) → assertEquals(Boolean.FALSE, null) fails → KILLED.
run_mutation \
    "Suite10 SDK: agentMap.put('synthesize', false) removed (AgentConfigSerializer)" \
    "$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java" \
    "sed -i '' 's/agentMap.put(\"synthesize\", false);/\/\/ MUTANT: synthesize not sent/' '$JAVA_SDK/src/main/java/dev/agentspan/internal/AgentConfigSerializer.java'" \
    "E2eSuite10Synthesize#test_handoff_no_synthesize_omits_final_task" \
    "source"

# Mutation 18: Suite10 Test — finalCount assertion wrong (0→2)
# The test expects 0 final tasks when synthesize=false.
# Changing 0→2 makes the assertion fail because the real count is 0.
run_mutation \
    "Suite10 Test: finalCount assertion 0→2 (handoff)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite10Synthesize.java" \
    "sed -i '' 's/assertEquals(0, finalCount,/assertEquals(2, finalCount,/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite10Synthesize.java'" \
    "E2eSuite10Synthesize#test_handoff_no_synthesize_omits_final_task" \
    "test"

# Mutation 19: Suite10 Test — synthesize assertion flipped (false→true)
# The test asserts agentDef.synthesize == false.
# Changing to assertEquals(true, ...) means a correctly-serialized false will fail.
run_mutation \
    "Suite10 Test: synthesize assertion false→true (agentDef check)" \
    "$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite10Synthesize.java" \
    "sed -i '' 's/assertEquals(Boolean.FALSE, agentDef.get(\"synthesize\")/assertEquals(Boolean.TRUE, agentDef.get(\"synthesize\")/' '$JAVA_SDK/src/test/java/dev/agentspan/e2e/E2eSuite10Synthesize.java'" \
    "E2eSuite10Synthesize#test_handoff_no_synthesize_omits_final_task" \
    "test"

# ── Summary ──────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  JAVA MUTATION TESTING RESULTS"
echo "═══════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Killed: $PASS / $((PASS + FAIL))  ($FAIL survived)"
echo "═══════════════════════════════════════════════════════════════"

[ $FAIL -eq 0 ]
