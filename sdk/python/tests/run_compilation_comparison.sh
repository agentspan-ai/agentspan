#!/usr/bin/env bash
# Run local vs server compilation comparison for all examples.
#
# Prerequisites:
#   1. Java runtime server built and ready
#   2. Python dependencies installed (pip install -e .)
#
# Usage:
#   cd python && bash tests/run_compilation_comparison.sh
#
# Or with a custom server URL:
#   SERVER_URL=http://myhost:8080/api bash tests/run_compilation_comparison.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_DIR="$(cd "$PYTHON_DIR/../runtime" && pwd)"
SERVER_URL="${SERVER_URL:-http://localhost:6767/api}"

# ── Colors ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Local vs Server Compilation Comparison ==="
echo ""

# ── Step 1: Check if server is running ───────────────────────────────────
echo -n "Checking server at ${SERVER_URL}... "
if curl -sf "${SERVER_URL}/health" > /dev/null 2>&1 || curl -sf "${SERVER_URL%/api}/actuator/health" > /dev/null 2>&1; then
    echo -e "${GREEN}running${NC}"
    SERVER_WAS_RUNNING=true
else
    echo -e "${YELLOW}not running${NC}"
    SERVER_WAS_RUNNING=false

    echo "Starting server from ${RUNTIME_DIR}..."
    cd "$RUNTIME_DIR"
    ./gradlew bootRun > /tmp/compilation-test-server.log 2>&1 &
    SERVER_PID=$!
    echo "Server PID: ${SERVER_PID}"

    # Wait for server to be ready (up to 60 seconds)
    echo -n "Waiting for server to start"
    for i in $(seq 1 30); do
        if lsof -i :8080 2>/dev/null | grep -q LISTEN; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done

    if ! lsof -i :8080 2>/dev/null | grep -q LISTEN; then
        echo -e " ${RED}FAILED${NC}"
        echo "Server failed to start. Check /tmp/compilation-test-server.log"
        exit 1
    fi
fi

# ── Step 2: Run comparison ───────────────────────────────────────────────
echo ""
echo "Running comparison..."
echo ""
cd "$PYTHON_DIR"

python3 tests/compare_compilation.py 2>&1
EXIT_CODE=$?

# ── Step 3: Show results ────────────────────────────────────────────────
echo ""
RESULTS_FILE="$PYTHON_DIR/tests/compilation_comparison.md"
if [ -f "$RESULTS_FILE" ]; then
    # Extract summary line
    SUMMARY=$(grep -E "^\*\*Total:" "$RESULTS_FILE" || true)
    if [ -n "$SUMMARY" ]; then
        MISMATCHES=$(echo "$SUMMARY" | grep -oE 'Mismatch: [0-9]+' | grep -oE '[0-9]+')
        if [ "$MISMATCHES" = "0" ]; then
            echo -e "${GREEN}${SUMMARY}${NC}"
        else
            echo -e "${RED}${SUMMARY}${NC}"
        fi
    fi
    echo ""
    echo "Full report: ${RESULTS_FILE}"
fi

# ── Step 4: Cleanup ─────────────────────────────────────────────────────
if [ "$SERVER_WAS_RUNNING" = false ] && [ -n "${SERVER_PID:-}" ]; then
    echo ""
    echo "Stopping server (PID: ${SERVER_PID})..."
    kill "$SERVER_PID" 2>/dev/null || true
fi

# Exit with failure if there were mismatches
if [ -n "${MISMATCHES:-}" ] && [ "$MISMATCHES" != "0" ]; then
    exit 1
fi

exit $EXIT_CODE
