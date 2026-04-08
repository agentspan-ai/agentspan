#!/usr/bin/env bash
set -uo pipefail

# Mutation testing for Suites 6 (PDF) and 7 (Media)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK_DIR="$REPO_ROOT/sdk/python"
PASS=0
FAIL=0
RESULTS=()

run_mutation() {
    local label="$1"
    local file="$2"
    local sed_cmd="$3"
    local suite_filter="$4"
    local full_path="$SDK_DIR/$file"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MUTATION: $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    cp "$full_path" "$full_path.bak"
    eval "$sed_cmd"

    local output exit_code
    output=$("$REPO_ROOT/e2e/orchestrator.sh" --suite "$suite_filter" 2>&1)
    exit_code=$?

    mv "$full_path.bak" "$full_path"

    if [ $exit_code -ne 0 ]; then
        local err
        err=$(echo "$output" | grep -E "AssertionError|Failed:|assert" | head -3)
        echo "  ✅ KILLED — test correctly failed"
        echo "  $err"
        RESULTS+=("✅ $label")
        ((PASS++))
    else
        # Check if the test was skipped (not a true pass)
        if echo "$output" | grep -q "0 passed"; then
            echo "  ⚠️  SKIPPED — test didn't run (not a survival)"
            RESULTS+=("⚠️  $label (skipped)")
        else
            echo "  ❌ SURVIVED — test did NOT catch the mutation!"
            RESULTS+=("❌ $label")
            ((FAIL++))
        fi
    fi
}

echo "═══════════════════════════════════════════════════════════════"
echo "  MUTATION TESTING — Suites 6 & 7"
echo "═══════════════════════════════════════════════════════════════"

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
echo "  MUTATION TESTING RESULTS — Suites 6 & 7"
echo "═══════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Killed: $PASS / $((PASS + FAIL))  ($FAIL survived)"
echo "═══════════════════════════════════════════════════════════════"

[ $FAIL -eq 0 ]
