#!/usr/bin/env bash
set -uo pipefail

# Mutation testing — proves tests catch bugs.
# Each mutation is applied, tested, then reverted via file backup.
#
# Usage:
#   ./e2e/mutation_test.sh              # all mutations (Python)
#   ./e2e/mutation_test.sh --sdk typescript  # all mutations (TypeScript)
#   ./e2e/mutation_test.sh --suite suite4    # only Suite 4 mutations

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK_DIR="$REPO_ROOT/sdk/python"
PASS=0
FAIL=0
SKIP=0
RESULTS=()
SDK_FLAG=""
SUITE_FLAG=""

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sdk)   SDK_FLAG="--sdk $2"; shift 2 ;;
    --suite) SUITE_FLAG="$2"; shift 2 ;;
    *)       echo "Unknown arg: $1"; exit 1 ;;
  esac
done

run_mutation() {
    local label="$1"
    local file="$2"       # relative to SDK_DIR
    local sed_cmd="$3"
    local suite_filter="$4"
    local full_path="$SDK_DIR/$file"

    # Skip if --suite flag doesn't match
    if [[ -n "$SUITE_FLAG" && "$suite_filter" != *"$SUITE_FLAG"* ]]; then
        return
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MUTATION: $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Backup → mutate → run → restore
    cp "$full_path" "$full_path.bak"
    eval "$sed_cmd"

    # Kill stray processes on test ports
    lsof -ti :3002 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti :3003 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti :3004 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti :3005 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 1

    local output exit_code
    output=$("$REPO_ROOT/e2e/orchestrator.sh" --no-build --no-start $SDK_FLAG --suite "$suite_filter" 2>&1)
    exit_code=$?

    # Always restore from backup
    mv "$full_path.bak" "$full_path"

    if [ $exit_code -ne 0 ]; then
        local err
        err=$(echo "$output" | grep -E "AssertionError|Failed:|assert|FAIL" | head -3)
        echo "  ✅ KILLED — test correctly failed"
        echo "  $err"
        RESULTS+=("✅ $label")
        ((PASS++))
    else
        # Check if the test was skipped (not a true pass)
        if echo "$output" | grep -q "0 passed"; then
            echo "  ⚠️  SKIPPED — test didn't run (not a survival)"
            RESULTS+=("⚠️  $label (skipped)")
            ((SKIP++))
        else
            echo "  ❌ SURVIVED — test did NOT catch the mutation!"
            RESULTS+=("❌ $label")
            ((FAIL++))
        fi
    fi
}

echo "═══════════════════════════════════════════════════════════════"
echo "  MUTATION TESTING — Proving tests catch bugs"
echo "═══════════════════════════════════════════════════════════════"

# ── Suite 4: MCP Tools ───────────────────────────────────────────

run_mutation \
    "Suite 4: wrong tool count (65→999)" \
    "e2e/test_suite4_mcp_tools.py" \
    "sed -i '' 's/== EXPECTED_TOOL_COUNT,/== 999,/g' '$SDK_DIR/e2e/test_suite4_mcp_tools.py'" \
    "suite4"

run_mutation \
    "Suite 4: wrong MCP URL (/mcp→/wrong)" \
    "e2e/test_suite4_mcp_tools.py" \
    "sed -i '' 's|/mcp\"|/wrong\"|' '$SDK_DIR/e2e/test_suite4_mcp_tools.py'" \
    "suite4"

run_mutation \
    "Suite 4: wrong expected output (olleh→hello)" \
    "e2e/test_suite4_mcp_tools.py" \
    "sed -i '' 's/\"string_reverse\": \"olleh\"/\"string_reverse\": \"hello\"/' '$SDK_DIR/e2e/test_suite4_mcp_tools.py'" \
    "suite4"

run_mutation \
    "Suite 4: wrong auth credential" \
    "e2e/test_suite4_mcp_tools.py" \
    "sed -i '' 's/cli_credentials.set(CRED_NAME, MCP_AUTH_KEY)/cli_credentials.set(CRED_NAME, \"wrong-key\")/' '$SDK_DIR/e2e/test_suite4_mcp_tools.py'" \
    "suite4"

# ── Suite 5: HTTP Tools ──────────────────────────────────────────

run_mutation \
    "Suite 5: wrong tool count (65→999)" \
    "e2e/test_suite5_http_tools.py" \
    "sed -i '' 's/== EXPECTED_TOOL_COUNT,/== 999,/g' '$SDK_DIR/e2e/test_suite5_http_tools.py'" \
    "suite5 and lifecycle"

run_mutation \
    "Suite 5: wrong HTTP endpoint (/add→/wrong)" \
    "e2e/test_suite5_http_tools.py" \
    "sed -i '' 's|/api/math/add|/api/math/wrong|' '$SDK_DIR/e2e/test_suite5_http_tools.py'" \
    "suite5 and lifecycle"

run_mutation \
    "Suite 5: wrong expected output (olleh→WRONG)" \
    "e2e/test_suite5_http_tools.py" \
    "sed -i '' 's/\"string_reverse\": \"olleh\"/\"string_reverse\": \"WRONG\"/' '$SDK_DIR/e2e/test_suite5_http_tools.py'" \
    "suite5 and lifecycle"

run_mutation \
    "Suite 5: wrong Orkes operationId" \
    "e2e/test_suite5_http_tools.py" \
    "sed -i '' 's/\"startWorkflow\"/\"wrongOp\"/g' '$SDK_DIR/e2e/test_suite5_http_tools.py'" \
    "suite5 and external"

# ── Suite 6: PDF Tools ───────────────────────────────────────────

run_mutation \
    "Suite 6: wrong tool (pdf_tool → image_tool)" \
    "e2e/test_suite6_pdf_tools.py" \
    "sed -i '' 's/from agentspan.agents import Agent, pdf_tool/from agentspan.agents import Agent, pdf_tool, image_tool/' '$SDK_DIR/e2e/test_suite6_pdf_tools.py' && sed -i '' 's/pdf = pdf_tool()/pdf = image_tool(name=\"wrong\", description=\"wrong\", llm_provider=\"openai\", model=\"dall-e-3\")/' '$SDK_DIR/e2e/test_suite6_pdf_tools.py'" \
    "suite6"

run_mutation \
    "Suite 6: wrong expected phrase (Agentspan → XYZNOTEXIST)" \
    "e2e/test_suite6_pdf_tools.py" \
    "sed -i '' 's/\"Agentspan E2E Test Report\"/\"XYZNOTEXIST_PHRASE\"/' '$SDK_DIR/e2e/test_suite6_pdf_tools.py'" \
    "suite6"

# ── Suite 7: Media Tools ────────────────────────────────────────

run_mutation \
    "Suite 7: wrong image model (dall-e-3 → nonexistent-model)" \
    "e2e/test_suite7_media_tools.py" \
    "sed -i '' '/test_image_openai/,/GENERATE_IMAGE/{s/model=\"dall-e-3\"/model=\"nonexistent-model\"/;}' '$SDK_DIR/e2e/test_suite7_media_tools.py'" \
    "suite7 and image_openai"

run_mutation \
    "Suite 7: wrong image provider (openai → fake_provider)" \
    "e2e/test_suite7_media_tools.py" \
    "sed -i '' '/test_image_openai/,/GENERATE_IMAGE/{s/llm_provider=\"openai\"/llm_provider=\"fake_provider\"/;}' '$SDK_DIR/e2e/test_suite7_media_tools.py'" \
    "suite7 and image_openai"

run_mutation \
    "Suite 7: wrong audio voice param (tts-1 → nonexistent)" \
    "e2e/test_suite7_media_tools.py" \
    "sed -i '' '/test_audio_openai/,/GENERATE_AUDIO/{s/model=\"tts-1\"/model=\"nonexistent-audio-model\"/;}' '$SDK_DIR/e2e/test_suite7_media_tools.py'" \
    "suite7 and audio"

run_mutation \
    "Suite 7: wrong task type assertion (GENERATE_IMAGE → GENERATE_VIDEO)" \
    "e2e/test_suite7_media_tools.py" \
    "sed -i '' '/test_image_openai/,/def test_image_gemini/{s/GENERATE_IMAGE/GENERATE_VIDEO/;}' '$SDK_DIR/e2e/test_suite7_media_tools.py'" \
    "suite7 and image_openai"

# ── Summary ──────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  MUTATION TESTING RESULTS"
echo "═══════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Killed: $PASS / $((PASS + FAIL))  ($FAIL survived, $SKIP skipped)"
echo "═══════════════════════════════════════════════════════════════"

[ $FAIL -eq 0 ]
