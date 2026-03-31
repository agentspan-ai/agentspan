#!/usr/bin/env bash
# run_examples.sh — Run all Agentspan Java SDK examples and report PASS/FAIL
# Usage: ./run_examples.sh [filter-pattern]
#   filter-pattern: optional substring to match against class name (e.g. "Example01")
#
# Environment:
#   AGENTSPAN_SERVER_URL  (default: http://localhost:6767)
#   EXAMPLE_TIMEOUT       per-example timeout in seconds (default: 120)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/examples"
SERVER_URL="${AGENTSPAN_SERVER_URL:-http://localhost:6767}"
DEFAULT_TIMEOUT="${EXAMPLE_TIMEOUT:-120}"
FILTER="${1:-}"
LOG_DIR="$SCRIPT_DIR/example-logs"
mkdir -p "$LOG_DIR"

# Returns custom timeout for known heavy examples, else DEFAULT_TIMEOUT
get_timeout() {
  case "$1" in
    Example13HierarchicalAgents)    echo 660 ;;  # deep 3-level hierarchy; client timeout is 10m
    Example68ContextCondensation)   echo 360 ;;
    Example55MlEngineeringPipeline) echo 360 ;;
    Example64SwarmWithTools)        echo 300 ;;
    Example12LongRunning)           echo 300 ;;
    Example38TechTrends)            echo 300 ;;
    Example54SoftwareBugAssistant)  echo 180 ;;
    Example45AgentTool)             echo 180 ;;
    Example58ScatterGather)         echo 300 ;;
    Example59CodingAgent)           echo 180 ;;
    *)                              echo "$DEFAULT_TIMEOUT" ;;
  esac
}

# Examples that require human-in-loop or external APIs not available — skipped
is_skip() {
  case "$1" in
    Example09HumanInTheLoop) return 0 ;;
    Example16CredentialsTool) return 0 ;;
    Example33ExternalWorkers) return 0 ;;
    Example18ManualSelection) return 0 ;;   # requires human to pick agent each turn
    Example32HumanGuardrail) return 0 ;;    # requires human approval in Conductor UI
    *) return 1 ;;
  esac
}

# Run a command with a timeout, killing the entire process group on expiry.
# Works on macOS (bash 3.2) without gtimeout/timeout.
run_with_timeout() {
  local secs="$1"; shift
  # Run command in background process group; kill group on timeout
  ("$@") &
  local child=$!
  (
    sleep "$secs"
    kill -TERM -"$child" 2>/dev/null
    sleep 2
    kill -KILL -"$child" 2>/dev/null
  ) &
  local killer=$!
  wait "$child" 2>/dev/null
  local rc=$?
  # Kill the killer if child finished naturally
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null
  return $rc
}

# Discover all example classes (sorted)
EXAMPLES=()
while IFS= read -r f; do
  cls=$(basename "$f" .java)
  EXAMPLES+=("$cls")
done < <(find "$EXAMPLES_DIR/src/main/java/dev/agentspan/examples" -name 'Example*.java' | sort)

echo "=============================================="
echo " Agentspan Java SDK — Example Runner"
echo " Server : $SERVER_URL"
echo " Default timeout: ${DEFAULT_TIMEOUT}s"
echo " Examples found : ${#EXAMPLES[@]}"
if [[ -n "$FILTER" ]]; then
  echo " Filter : $FILTER"
fi
echo "=============================================="
echo ""

PASS=0
FAIL=0
SKIP_COUNT=0
declare -a RESULTS

for cls in "${EXAMPLES[@]}"; do

  # Apply filter
  if [[ -n "$FILTER" && "$cls" != *"$FILTER"* ]]; then
    continue
  fi

  # Check skip list
  if is_skip "$cls"; then
    printf "  %-52s SKIP  (requires external resource)\n" "$cls"
    RESULTS+=("SKIP  $cls")
    SKIP_COUNT=$((SKIP_COUNT + 1))
    continue
  fi

  t=$(get_timeout "$cls")
  log="$LOG_DIR/${cls}.log"

  printf "  %-52s " "$cls"

  # Run with timeout — captures stdout+stderr to log, tracks exit code
  exit_code=0
  run_with_timeout "$t" bash -c "
    cd '$EXAMPLES_DIR' && \
    AGENTSPAN_SERVER_URL='$SERVER_URL' \
    mvn -q exec:java \
      -Dexec.mainClass='dev.agentspan.examples.$cls' \
      -Dorg.slf4j.simpleLogger.defaultLogLevel=warn
  " > "$log" 2>&1 || exit_code=$?

  # Determine result
  if grep -q "Status: COMPLETED" "$log" 2>/dev/null; then
    echo "PASS"
    RESULTS+=("PASS  $cls")
    PASS=$((PASS + 1))
  elif grep -qE "timed out after|Agent timed out" "$log" 2>/dev/null; then
    echo "TIMEOUT (${t}s — client limit)"
    RESULTS+=("TIMEOUT $cls")
    FAIL=$((FAIL + 1))
  elif grep -qE "Status: FAILED|Exception in thread|BUILD FAILURE" "$log" 2>/dev/null; then
    echo "FAIL  (see example-logs/${cls}.log)"
    RESULTS+=("FAIL  $cls")
    FAIL=$((FAIL + 1))
  elif [[ $exit_code -ne 0 ]]; then
    # exit_code 143 = SIGTERM (timeout kill); treat as TIMEOUT
    if [[ $exit_code -eq 143 || $exit_code -eq 137 ]]; then
      echo "TIMEOUT (${t}s)"
      RESULTS+=("TIMEOUT $cls")
    else
      echo "FAIL  exit=$exit_code (see example-logs/${cls}.log)"
      RESULTS+=("FAIL  $cls")
    fi
    FAIL=$((FAIL + 1))
  else
    echo "PASS  (no status line)"
    RESULTS+=("PASS  $cls")
    PASS=$((PASS + 1))
  fi

done

TOTAL=$((PASS + FAIL + SKIP_COUNT))

echo ""
echo "=============================================="
echo " RESULTS SUMMARY"
echo "=============================================="
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""
echo "  PASS   : $PASS"
echo "  FAIL   : $FAIL"
echo "  SKIP   : $SKIP_COUNT"
echo "  TOTAL  : $TOTAL"
echo "=============================================="

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "Logs for failed examples: $LOG_DIR/"
  exit 1
fi
exit 0
