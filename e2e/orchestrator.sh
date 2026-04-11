#!/usr/bin/env bash
set -euo pipefail

# ── E2E Test Orchestrator ────────────────────────────────────────────────
# Builds all components, starts services, runs e2e tests, generates report.
#
# Usage:
#   ./e2e/orchestrator.sh              # defaults: -j 1
#   ./e2e/orchestrator.sh -j 4        # 4 parallel workers
#   ./e2e/orchestrator.sh --suite suite1
#   ./e2e/orchestrator.sh --no-build --no-start

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_DIR="$REPO_ROOT/e2e-results"
PARALLELISM=1
SUITE_FILTER=""
DO_BUILD=true
DO_START=true
SERVER_PORT=6767
MCP_PORT=3001
SERVER_PID=""
MCP_PID=""

# ── Parse arguments ─────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    -j|--parallelism) PARALLELISM="$2"; shift 2 ;;
    --suite)          SUITE_FILTER="$2"; shift 2 ;;
    --no-build)       DO_BUILD=false; shift ;;
    --no-start)       DO_START=false; shift ;;
    --port)           SERVER_PORT="$2"; shift 2 ;;
    --mcp-port)       MCP_PORT="$2"; shift 2 ;;
    *)                echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Cleanup trap ────────────────────────────────────────────────────────

cleanup() {
  # Disable errexit inside cleanup — we must not let kill/wait failures
  # override the real exit code captured in TEST_EXIT.
  set +e
  echo ""
  echo "=== Teardown ==="
  if [[ -n "$SERVER_PID" ]]; then
    echo "Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [[ -n "$MCP_PID" ]]; then
    echo "Stopping mcp-testkit (PID $MCP_PID)..."
    kill "$MCP_PID" 2>/dev/null
    wait "$MCP_PID" 2>/dev/null
  fi
  echo "Done."
}
trap cleanup EXIT

# ── Build ───────────────────────────────────────────────────────────────

if $DO_BUILD; then
  echo "=== Building server ==="
  cd "$REPO_ROOT/server"
  ./gradlew bootJar -x test -q
  echo "Server JAR built."

  echo "=== Building CLI ==="
  cd "$REPO_ROOT/cli"
  go build -o agentspan .
  echo "CLI built at cli/agentspan"

  echo "=== Installing Python SDK ==="
  cd "$REPO_ROOT/sdk/python"
  uv sync --extra dev --extra testing -q
  echo "Python SDK installed."

  echo "=== Installing mcp-testkit ==="
  uv pip install mcp-testkit -q 2>/dev/null || pip install mcp-testkit -q
  echo "mcp-testkit installed."
fi

# ── Start services ──────────────────────────────────────────────────────

if $DO_START; then
  echo "=== Starting mcp-testkit on port $MCP_PORT ==="
  mcp-testkit --transport http --port "$MCP_PORT" &
  MCP_PID=$!
  echo "mcp-testkit started (PID $MCP_PID)"

  echo "=== Starting agentspan server on port $SERVER_PORT ==="
  java -jar "$REPO_ROOT/server/build/libs/agentspan-runtime.jar" \
    --server.port="$SERVER_PORT" &
  SERVER_PID=$!
  echo "Server started (PID $SERVER_PID)"

  echo "=== Waiting for server health ==="
  for i in $(seq 1 30); do
    if curl -sf "http://localhost:$SERVER_PORT/health" > /dev/null 2>&1; then
      echo "Server healthy."
      break
    fi
    if [[ $i -eq 30 ]]; then
      echo "ERROR: Server did not become healthy in 60s"
      exit 1
    fi
    sleep 2
  done

  echo "=== Waiting for mcp-testkit ==="
  for i in $(seq 1 15); do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$MCP_PORT/" 2>/dev/null | grep -q "[0-9]"; then
      echo "mcp-testkit healthy."
      break
    fi
    if [[ $i -eq 15 ]]; then
      echo "ERROR: mcp-testkit did not start in 30s"
      exit 1
    fi
    sleep 2
  done
fi

# ── Run tests ───────────────────────────────────────────────────────────

echo "=== Running E2E tests (parallelism=$PARALLELISM) ==="
mkdir -p "$RESULTS_DIR"

export AGENTSPAN_SERVER_URL="http://localhost:$SERVER_PORT/api"
export AGENTSPAN_CLI_PATH="$REPO_ROOT/cli/agentspan"
export MCP_TESTKIT_URL="http://localhost:$MCP_PORT"
export AGENTSPAN_AUTO_START_SERVER=false

# Build pytest args
PYTEST_ARGS=(
  "$REPO_ROOT/sdk/python/e2e/"
  "-v"
  "--tb=short"
  "--junitxml=$RESULTS_DIR/junit.xml"
  "-n" "$PARALLELISM"
)

if [[ -n "$SUITE_FILTER" ]]; then
  PYTEST_ARGS+=("-k" "$SUITE_FILTER")
fi

cd "$REPO_ROOT/sdk/python"
TEST_EXIT=0
uv run pytest "${PYTEST_ARGS[@]}" || TEST_EXIT=$?

# ── Generate HTML report ────────────────────────────────────────────────

echo "=== Generating HTML report ==="
uv run python "$REPO_ROOT/sdk/python/e2e/report_generator.py" \
  "$RESULTS_DIR/junit.xml" "$RESULTS_DIR/report.html"

echo ""
echo "=============================="
echo "  Results: $RESULTS_DIR/report.html"
echo "  XML:     $RESULTS_DIR/junit.xml"
echo "=============================="

exit $TEST_EXIT
