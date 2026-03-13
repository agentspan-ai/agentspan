#!/usr/bin/env bash
#
# Run all examples and report failures.
#
# Usage:
#   ./scripts/run_examples.sh              # run all non-interactive examples
#   ./scripts/run_examples.sh --all        # include interactive/external-dep examples
#   ./scripts/run_examples.sh 01 02 10     # run only matching examples (prefix match)
#
# Requires:
#   export AGENTSPAN_SERVER_URL=http://localhost:8080/api
#
# Exit code: 0 if all passed, 1 if any failed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXAMPLES_DIR="$(cd "$SCRIPT_DIR/../examples" && pwd)"
TIMEOUT="${EXAMPLE_TIMEOUT:-300}"

# Examples that require external services not typically available in a
# standard test environment.
SKIP_BY_DEFAULT=(
    "04_http_and_mcp_tools"    # needs MCP server running
    "04_mcp_weather"           # needs MCP server running
    "24_code_execution"        # needs Docker
    "25_semantic_memory"       # needs vector store / extra deps
    "26_opentelemetry_tracing" # needs OTel collector
    "28_gpt_assistant_agent"   # needs OpenAI Assistants API key
)

# HITL examples that call input() — we pipe automated responses via stdin.
# Format: "example_prefix:response_lines"
# Each response line is separated by \n and fed to successive input() calls.
declare -A HITL_STDIN=(
    ["02_tools"]="y"                          # approve send_email
    ["09_human_in_the_loop"]="y"              # approve transfer_funds
    ["09b_hitl_with_feedback"]="a"            # approve article publication
    ["09c_hitl_streaming"]="y"                # approve delete_service_data
)

# ── Parse args ───────────────────────────────────────────────────────────

INCLUDE_ALL=false
FILTER_PREFIXES=()

for arg in "$@"; do
    if [[ "$arg" == "--all" ]]; then
        INCLUDE_ALL=true
    else
        FILTER_PREFIXES+=("$arg")
    fi
done

# ── Collect examples ─────────────────────────────────────────────────────

should_skip() {
    local basename="$1"
    if $INCLUDE_ALL; then
        return 1
    fi
    for skip in "${SKIP_BY_DEFAULT[@]}"; do
        if [[ "$basename" == "$skip" ]]; then
            return 0
        fi
    done
    return 1
}

matches_filter() {
    local basename="$1"
    if [[ ${#FILTER_PREFIXES[@]} -eq 0 ]]; then
        return 0  # no filter = match all
    fi
    for prefix in "${FILTER_PREFIXES[@]}"; do
        if [[ "$basename" == "$prefix"* ]]; then
            return 0
        fi
    done
    return 1
}

EXAMPLES=()
SKIPPED=()

for f in "$EXAMPLES_DIR"/[0-9]*.py; do
    basename="$(basename "$f" .py)"
    if ! matches_filter "$basename"; then
        continue
    fi
    if should_skip "$basename"; then
        SKIPPED+=("$basename")
        continue
    fi
    EXAMPLES+=("$f")
done

if [[ ${#EXAMPLES[@]} -eq 0 ]]; then
    echo "No examples to run."
    exit 0
fi

# ── Run ──────────────────────────────────────────────────────────────────

PASSED=()
FAILED=()
FAILED_NAMES=()

echo "=========================================="
echo " Running ${#EXAMPLES[@]} examples"
if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    echo " Skipping ${#SKIPPED[@]}: ${SKIPPED[*]}"
fi
echo " Timeout: ${TIMEOUT}s per example"
echo "=========================================="
echo ""

for example in "${EXAMPLES[@]}"; do
    name="$(basename "$example" .py)"
    printf "%-45s " "$name"

    LOG_FILE=$(mktemp "/tmp/example-${name}-XXXXXX")

    START_TIME=$(date +%s)

    # Check if this HITL example needs automated stdin input
    STDIN_RESPONSE=""
    for hitl_prefix in "${!HITL_STDIN[@]}"; do
        if [[ "$name" == "$hitl_prefix"* ]]; then
            STDIN_RESPONSE="${HITL_STDIN[$hitl_prefix]}"
            break
        fi
    done

    if [[ -n "$STDIN_RESPONSE" ]]; then
        RUN_CMD="printf '%s\n' $STDIN_RESPONSE | timeout $TIMEOUT python3 $example"
    else
        RUN_CMD="timeout $TIMEOUT python3 $example"
    fi

    if eval "$RUN_CMD" > "$LOG_FILE" 2>&1; then
        ELAPSED=$(( $(date +%s) - START_TIME ))
        # Extract workflow ID from output
        WF_ID=$(sed -n 's/.*Workflow ID: \([^ ]*\).*/\1/p' "$LOG_FILE" | tail -1 || true)
        if [[ -n "$WF_ID" ]]; then
            echo "PASS (${ELAPSED}s) workflow=$WF_ID"
        else
            echo "PASS (${ELAPSED}s)"
        fi
        PASSED+=("$name")
        rm -f "$LOG_FILE"
    else
        EXIT_CODE=$?
        ELAPSED=$(( $(date +%s) - START_TIME ))
        if [[ $EXIT_CODE -eq 124 ]]; then
            echo "TIMEOUT (${TIMEOUT}s)"
        else
            echo "FAIL (exit $EXIT_CODE, ${ELAPSED}s)"
        fi
        FAILED+=("$name")
        FAILED_NAMES+=("$name ($LOG_FILE)")
    fi
done

# ── Summary ──────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo " Results: ${#PASSED[@]} passed, ${#FAILED[@]} failed, ${#SKIPPED[@]} skipped"
echo "=========================================="

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "FAILED examples:"
    for entry in "${FAILED_NAMES[@]}"; do
        echo "  - $entry"
    done

    # ── Detailed failure info ────────────────────────────────────────
    echo ""
    echo "=========================================="
    echo " Failure Details"
    echo "=========================================="
    for entry in "${FAILED_NAMES[@]}"; do
        # Parse "name (logfile)" format
        FAIL_NAME="${entry%% (*}"
        FAIL_LOG="${entry##*(}"
        FAIL_LOG="${FAIL_LOG%)}"

        echo ""
        echo "── $FAIL_NAME ──"

        # Show last few lines of stderr/stdout for the error
        if [[ -f "$FAIL_LOG" ]]; then
            # Extract workflow ID from log
            WF_ID=$(sed -n 's/.*Workflow ID: \([^ ]*\).*/\1/p' "$FAIL_LOG" | tail -1 || true)
            # Show Python traceback or last error lines
            ERROR_LINES=$(grep -A2 'Traceback\|Error\|Exception\|FAIL\|WARN' "$FAIL_LOG" | tail -10 || true)
            if [[ -n "$ERROR_LINES" ]]; then
                echo "  Error:"
                echo "$ERROR_LINES" | sed 's/^/    /'
            else
                echo "  Last output:"
                tail -5 "$FAIL_LOG" | sed 's/^/    /'
            fi

            # Query Conductor for workflow status if we have an ID and server URL
            if [[ -n "$WF_ID" && -n "${AGENTSPAN_SERVER_URL:-}" ]]; then
                echo "  Workflow: $WF_ID"
                # Use the SDK's own client so auth (key/secret → token) is handled
                WF_INFO=$(python3 -c "
import os, json
try:
    from agentspan.agents.runtime.config import AgentConfig
    cfg = AgentConfig()
    configuration = cfg.to_conductor_configuration()
    from conductor.client.orkes_clients import OrkesClients
    client = OrkesClients(configuration=configuration).get_workflow_client()
    wf = client.get_workflow(workflow_id='$WF_ID', include_tasks=True)
    status = getattr(wf, 'status', 'UNKNOWN')
    reason = getattr(wf, 'reason_for_incompletion', '') or ''
    failed_tasks = getattr(wf, 'failed_reference_task_names', '') or ''
    # Find the last failed task's reason
    task_reason = ''
    for t in reversed(getattr(wf, 'tasks', []) or []):
        t_status = getattr(t, 'status', '')
        if t_status in ('FAILED', 'FAILED_WITH_TERMINAL_ERROR', 'TIMED_OUT'):
            t_reason = getattr(t, 'reason_for_incompletion', '') or ''
            t_name = getattr(t, 'reference_task_name', '') or getattr(t, 'task_def_name', '')
            task_reason = f'{t_name}: {t_reason}' if t_reason else t_name
            break
    print(json.dumps({
        'status': status,
        'reason': reason,
        'failed_tasks': failed_tasks,
        'task_reason': task_reason,
    }))
except Exception as e:
    print(json.dumps({'error': str(e)}))
" 2>/dev/null || echo '{"error":"query failed"}')
                WF_STATUS=$(echo "$WF_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
                WF_REASON=$(echo "$WF_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reason',''))" 2>/dev/null || true)
                WF_FAILED_TASKS=$(echo "$WF_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed_tasks',''))" 2>/dev/null || true)
                WF_TASK_REASON=$(echo "$WF_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_reason',''))" 2>/dev/null || true)
                WF_ERROR=$(echo "$WF_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))" 2>/dev/null || true)

                if [[ -n "$WF_ERROR" ]]; then
                    echo "  (could not query Conductor: $WF_ERROR)"
                else
                    echo "  Status:       $WF_STATUS"
                    [[ -n "$WF_REASON" ]]       && echo "  Reason:       $WF_REASON"
                    [[ -n "$WF_FAILED_TASKS" ]] && echo "  Failed tasks: $WF_FAILED_TASKS"
                    [[ -n "$WF_TASK_REASON" ]]  && echo "  Task detail:  $WF_TASK_REASON"
                fi
            elif [[ -n "$WF_ID" ]]; then
                echo "  Workflow: $WF_ID"
                echo "  (set AGENTSPAN_SERVER_URL to query workflow status)"
            fi
        fi
    done
    echo ""
    echo "Logs preserved in /tmp/example-*"
    exit 1
fi

exit 0
