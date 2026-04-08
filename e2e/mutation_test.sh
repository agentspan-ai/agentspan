#!/usr/bin/env bash
set -uo pipefail

# Mutation testing — proves tests catch bugs.
# Each mutation is applied, tested, then reverted via file backup.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK_DIR="$REPO_ROOT/sdk/python"
PASS=0
FAIL=0
RESULTS=()

run_mutation() {
    local label="$1"
    local file="$2"       # relative to SDK_DIR
    local sed_cmd="$3"
    local suite_filter="$4"
    local full_path="$SDK_DIR/$file"

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
    sleep 1

    local output exit_code
    output=$("$REPO_ROOT/e2e/orchestrator.sh" --suite "$suite_filter" 2>&1)
    exit_code=$?

    # Always restore from backup
    mv "$full_path.bak" "$full_path"

    if [ $exit_code -ne 0 ]; then
        local err
        err=$(echo "$output" | grep -E "AssertionError|Failed:|assert" | head -3)
        echo "  ✅ KILLED — test correctly failed"
        echo "  $err"
        RESULTS+=("✅ $label")
        ((PASS++))
    else
        echo "  ❌ SURVIVED — test did NOT catch the mutation!"
        RESULTS+=("❌ $label")
        ((FAIL++))
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

# ── Summary ──────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  MUTATION TESTING RESULTS"
echo "═══════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Killed: $PASS / $((PASS + FAIL))  ($FAIL survived)"
echo "═══════════════════════════════════════════════════════════════"

[ $FAIL -eq 0 ]
